import os
import sys
from typing import Union

import onnx
import tensorrt as trt
from onnxconverter_common import float16

from if_rest.logger import logger

# Based on code from NVES_R's response at
# https://forums.developer.nvidia.com/t/segmentation-fault-when-creating-the-trt-builder-in-python-works-fine-with-trtexec/111376


TRT_LOGGER = trt.Logger(trt.Logger.WARNING)


def _build_engine_onnx(input_onnx: bytes, force_fp16: bool = False, max_batch_size: int = 1,
                       max_workspace: int = 1024):
    """
    Builds TensorRT engine from provided ONNX file

    Args:
        input_onnx (bytes): serialized ONNX model.
        force_fp16 (bool): Build in FP16 precision.
        max_batch_size (int): Define maximum batch size supported by engine. If >1 creates optimization profile.
        max_workspace (int): Maximum builder workspace in MB.

    Returns:
        Serialized TensorRT engine
    """

    # TensorRT 11 dropped the FP16 builder flag: networks are strongly typed, so precision comes from the ONNX
    # types. Inputs and outputs stay FP32, so the inference code is unchanged.
    if force_fp16:
        logger.info('Building TensorRT engine in FP16 (ONNX weights converted to FP16).')
        model = float16.convert_float_to_float16(onnx.load_from_string(input_onnx), keep_io_types=True)
        input_onnx = model.SerializeToString()
    else:
        logger.warning('Building engine in FP32 mode.')

    flags = 1 << int(trt.NetworkDefinitionCreationFlag.STRONGLY_TYPED)
    with trt.Builder(TRT_LOGGER) as builder, \
            builder.create_network(flags) as network, \
            builder.create_builder_config() as config, \
            trt.OnnxParser(network, TRT_LOGGER) as parser:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, max_workspace * 1024 * 1024)
        if not parser.parse(input_onnx):
            print('ERROR: Failed to parse the ONNX')
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            sys.exit(1)

        if max_batch_size != 1:
            logger.warning('Batch size !=1 is used. Ensure your inference code supports it.')
        profile = builder.create_optimization_profile()
        # Get input name and shape for building optimization profile
        input = network.get_input(0)
        inp_shape = list(input.shape)
        inp_shape[0] = 1
        min_opt_shape = tuple(inp_shape)
        inp_shape[0] = max_batch_size
        max_shape = tuple(inp_shape)
        input_name = input.name
        profile.set_shape(input_name, min_opt_shape, min_opt_shape, max_shape)
        config.add_optimization_profile(profile)
        return builder.build_serialized_network(network, config)


def check_fp16():
    """
    Every GPU TensorRT 11 supports has fast FP16, and TensorRT 11 no longer reports it.

    Returns:
        bool: True
    """
    return True


def convert_onnx(input_onnx: Union[str, bytes], engine_file_path: str, force_fp16: bool = False,
                 max_batch_size: int = 1):
    """
    Creates TensorRT engine and serializes it to disk

    Args:
        input_onnx (Union[str, bytes]): Path to ONNX file on disk or serialized ONNX model.
        engine_file_path (str): Path where TensorRT engine should be saved.
        force_fp16 (bool): Build in FP16 precision.
        max_batch_size (int): Define maximum batch size supported by engine. If >1 creates optimization profile.

    Returns:
        None
    """

    onnx_obj = None
    if isinstance(input_onnx, str):
        with open(input_onnx, "rb") as f:
            onnx_obj = f.read()
    elif isinstance(input_onnx, bytes):
        onnx_obj = input_onnx

    engine = _build_engine_onnx(input_onnx=onnx_obj, force_fp16=force_fp16, max_batch_size=max_batch_size)

    assert not isinstance(engine, type(None))

    # Workers sharing /models build the same engine at first start: write a private file, then swap it in, so no
    # worker ever loads a half-written engine.
    temp_path = f"{engine_file_path}.{os.getpid()}.tmp"
    with open(temp_path, "wb") as f:
        f.write(engine)
    os.replace(temp_path, engine_file_path)
