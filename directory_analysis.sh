#!/bin/bash

# Directory to analyze
DIRECTORY=$1
OUTPUT_FILE=$2

# Check if directory is provided
if [ -z "$DIRECTORY" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "Usage: $0 /path/to/directory output.csv"
    exit 1
fi

# Initialize variables
total_images=0
total_subdirs=0
invalid_subdirs=0

# Start writing the CSV header
echo "Subdirectory,Image Count,Valid (Yes/No)" > "$OUTPUT_FILE"

# Process subdirectories
for dir in "$DIRECTORY"/*; do
    if [ -d "$dir" ]; then
        total_subdirs=$((total_subdirs + 1))
        # Count images in the current subdirectory
        image_count=$(find "$dir" -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l)
        total_images=$((total_images + image_count))

        # Check validity of image count
        if [ "$image_count" -eq 5 ] || [ "$image_count" -eq 10 ]; then
            valid="Yes"
        else
            valid="No"
            invalid_subdirs=$((invalid_subdirs + 1))
        fi

        # Append to CSV
        echo "$(basename "$dir"),$image_count,$valid" >> "$OUTPUT_FILE"
    fi
done

# shellcheck disable=SC2129
echo "" >> "$OUTPUT_FILE"

# Append summary to the CSV
echo "Total Subdirectories,$total_subdirs," >> "$OUTPUT_FILE"
echo "Total Images,$total_images," >> "$OUTPUT_FILE"
echo "Total Invalid Subdirectories,$invalid_subdirs," >> "$OUTPUT_FILE"

# Final message
echo "Analysis complete. Results saved in $OUTPUT_FILE."
