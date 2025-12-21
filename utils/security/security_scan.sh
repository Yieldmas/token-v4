aderyn && mv report.md security-reports/aderyn.md
myth analyze src/*.sol --solc-json mythril.solc.json --format json > security-reports/myth.txt
slither . --checklist > security-reports/slither.md
solidity-code-metrics src/**/*.sol --html > security-reports/solidty-metrics.html