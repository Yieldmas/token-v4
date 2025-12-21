#!/bin/bash

# Directories and Output Setup
SRC_DIR="./src"
OUTPUT_DIR="./docs/graphs"

# Create output directory for DOT files if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Function to process contracts
process_contracts() {
  local dir="$1"
  
  echo "Processing contracts in $dir..."

  # Find all .sol files in the directory and process them
  find "$dir" -name "*.sol" | while read -r contract; do
    contract_name=$(basename "$contract" .sol)

    # Skip Facets in the `core` folder
    if [[ "$contract" == *"/core/"* ]]; then
      echo "Skipping core Facet: $contract_name"
      continue
    fi

    # Skip interfaces starting with "I"
    if [[ "$contract_name" == I* ]]; then
      echo "Skipping interface: $contract_name"
      continue
    fi

    echo "Generating DOT file for $contract_name..."

    # Run `surya graph` and save DOT file directly in OUTPUT_DIR
    surya graph "$contract" > "$OUTPUT_DIR/${contract_name}_call_graph.dot"
  done
}

# Start the analysis
process_contracts "$SRC_DIR"

echo "DOT files generated. Outputs are in $OUTPUT_DIR."
