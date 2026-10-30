import multiprocessing


# Python 3.14 defaults to forkserver; the workers receive live Milvus collections, which must be inherited by fork.
# Must stay above the queue: creating it fixes the start method for the whole process.
multiprocessing.set_start_method("fork")

MULTIPROCESS_SHARED_BUFFER = multiprocessing.Queue()
