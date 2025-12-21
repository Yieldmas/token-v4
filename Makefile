# Comprehensive Solidity Project Makefile

# Define directories and paths
CONTRACTS_DIR = src/
OUTPUT_DIR = selectors
BASH_SCRIPTS_DIR = utils
SOLIDITY_FILES = $(shell find src -name "*.sol")
DAPP_SRC := src
TEST_SRC := test
COVERAGE_DIR := coverage
AUDIT_DIR := audit
REPORT_DIR := reports
COVERAGE_FILTER := "(test/|dependencies/|script/|mock/|core/|prb-math/|node_modules/|src/utils/)"
FILTER_PATHS := "@openzeppelin|@uniswap"

# Define phony targets
.PHONY: all test coverage report audit clean help extract_interface extract_selectors extract_selector verify_contract move_abi lint lint-fix

# Default target
all: extract_selectors move_abi lint

# Help command
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development Targets:"
	@echo "  all              - Run extract_selectors, move_abi, and lint"
	@echo "  extract_selectors - Extract selectors from contracts"
	@echo "  extract_interface - Extract Dayhub interface"
	@echo "  move_abi         - Move ABI files to abis directory"
	@echo ""
	@echo "Testing & Analysis Targets:"
	@echo "  test             - Run tests with verbose output"
	@echo "  coverage         - Show coverage summary"
	@echo "  report           - Generate and open coverage report"
	@echo "  audit            - Run security analysis (Aderyn & Solhint)"
	@echo "  snapshot         - Create gas snapshot"
	@echo ""
	@echo "Utility Targets:"
	@echo "  clean            - Remove all build and generated files"
	@echo "  dirs             - Create all necessary directories"

extract_interface:
	@echo "🔍 Extracting interface..."
	@cast interface src/diamond/facets/Dayhub.sol > temp.sol
	@mv temp.sol src/diamond/interfaces/IDayhub.sol


extract_selectors:
	@echo "🔍 Extracting selectors..."
	@bash ./utils/diamond/extract_selectors.sh

extract_selector:
	@echo "🔍 Extracting selectors..."
	@test -n "$(file)" || { echo "Usage: make extract_selector file=ContractNameOrPath"; exit 1; }
	@bash ./utils/diamond/extract_selectors.sh --file "$(file)"


move_abi: dirs
	@echo "📄 Moving ABI files..."
	@mkdir -p abis
	@jq '.abi' out/ChallengeAbi.sol/ChallengeAbi.json > abis/ChallengeAbi.json 2>/dev/null || echo "Warning: Challenge.json not found"


coverage: 
	@echo "📊 Running coverage analysis..."
	@forge coverage --no-match-coverage $(COVERAGE_FILTER) --ir-minimum

report: dirs
	@echo "📈 Generating LCOV report..."
	@forge coverage --ir-minimum --no-match-coverage $(COVERAGE_FILTER) --report lcov >/dev/null && mv lcov.info $(COVERAGE_DIR)/lcov.info
	@echo "🖨️  Building HTML report..."
	@genhtml $(COVERAGE_DIR)/lcov.info --output-directory $(COVERAGE_DIR) --ignore-errors inconsistent >/dev/null
	@echo "🚀 Report generated in $(COVERAGE_DIR)/"
	@echo "✅ Opening report..."
	@sleep 1.5
	@open $(COVERAGE_DIR)/index.html 2>/dev/null || xdg-open $(COVERAGE_DIR)/index.html 2>/dev/null || echo "Could not open browser automatically. Please open $(COVERAGE_DIR)/index.html manually."

audit: dirs
	@echo "🛡️  Running security audit..."
	@mkdir -p $(AUDIT_DIR)
	@echo "Running Aderyn..."
	@aderyn . -x utils > /dev/null 2>&1 && mv report.md $(AUDIT_DIR)/aderyn.md 2>/dev/null || echo "Warning: Aderyn failed or not installed"
	@echo "Running Slither..."
	-@slither . --filter-paths $(FILTER_PATHS) --checklist > $(AUDIT_DIR)/slither.md 2>/dev/null
	@echo "🔍 Running Solhint..."
	@mkdir -p $(AUDIT_DIR)
	@solhint --config config/security/solhint.json $(shell find src -name "*.sol") -f json > $(AUDIT_DIR)/solhint-report.json
	@python ${BASH_SCRIPTS_DIR}/convert_solhint_report.py $(AUDIT_DIR)/solhint-report.json $(AUDIT_DIR)/solhint-report.md
	@echo "📊 Solhint report generated at $(AUDIT_DIR)/solhint-report.md"
	@rm $(AUDIT_DIR)/solhint-report.json
	@echo "✅ Audit reports generated in $(AUDIT_DIR)/"



# Directory creation and cleanup
dirs:
	@mkdir -p $(COVERAGE_DIR) $(AUDIT_DIR) $(REPORT_DIR) abis $(OUTPUT_DIR)

clean:
	@echo "🧹 Cleaning up..."
	@forge clean
	@forge cache clean
	@rm -rf $(COVERAGE_DIR) $(AUDIT_DIR) $(REPORT_DIR) abis $(OUTPUT_DIR)/*.json



# Include the shell scripts as dependencies
$(BASH_SCRIPTS_DIR)/extract_selectors.sh:
	@echo "❌ Shell script $(BASH_SCRIPTS_DIR)/extract_selectors.sh not found!"
	@exit 1

$(BASH_SCRIPTS_DIR)/verify_contract.sh:
	@echo "❌ Shell script $(BASH_SCRIPTS_DIR)/verify_contract.sh not found!"
	@exit 1

$(BASH_SCRIPTS_DIR)/solhint_md.sh:
	@echo "❌ Shell script $(BASH_SCRIPTS_DIR)/solhint_md.sh not found!"
	@exit 1

.DELETE_ON_ERROR: