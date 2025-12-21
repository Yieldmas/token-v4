#!/usr/bin/env node
import { execSync } from "child_process";

function main() {
  const result = {
    facet: null,
    address: null,
    commit: execSync("git rev-parse HEAD", { encoding: "utf8" }).trim(),
  };

  console.log(JSON.stringify(result));
}

main();
