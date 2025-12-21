#!/usr/bin/env bash

# Extract deployed contract names and addresses from the JSON file
jq -r '.transactions[] | "\(.contractName) \(.contractAddress)"' broadcast/Deploy.s.sol/8453/run-latest.json > deployments/8453.deployed.json