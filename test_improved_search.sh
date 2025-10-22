#!/bin/bash
# ================================================================
# KB Search - Test Improved Search Module v2.0
# ================================================================
# Testa le funzionalità di improvement:
# - Deduplicazione versioni
# - Filtro temporale smart
# - Stopwords removal
# - Backward compatibility
# ================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
API_URL="http://localhost:8000"
PASSED=0
FAILED=0

# Functions
log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[✓ PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[✗ FAIL]${NC} $1"
    ((FAILED++))
}

log_info() {
    echo -e "  ${BLUE}→${NC} $1"
}

# === TEST SUITE ===

echo ""
echo "================================================================"
echo "  KB Search - Test Improved Search v2.0"
echo "================================================================"
echo ""

# Test 0: API Health
log_test "0. API Health Check"
if curl -sf "$API_URL/health" > /dev/null 2>&1; then
    log_pass "API is healthy"
else
    log_fail "API not responding!"
    exit 1
fi
echo ""

# Test 1: Basic Search (backward compatibility)
log_test "1. Basic Search (Backward Compatibility)"
RESPONSE=$(curl -sf "$API_URL/search?q_text=test&top_k=5" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Basic search works"
    TOTAL=$(echo "$RESPONSE" | jq -r '.total' 2>/dev/null || echo "0")
    log_info "Returned: $TOTAL results"
else
    log_fail "Basic search failed"
    log_info "Response: $RESPONSE"
fi
echo ""

# Test 2: Search with deduplicate parameter
log_test "2. Deduplication Parameter"
RESPONSE=$(curl -sf "$API_URL/search?q_text=piano&top_k=20&deduplicate=true" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Deduplicate parameter accepted"
    
    # Check if enhancement metadata present
    if echo "$RESPONSE" | jq -e '.enhancement' > /dev/null 2>&1; then
        REMOVED=$(echo "$RESPONSE" | jq -r '.enhancement.removed_duplicates // 0' 2>/dev/null)
        log_info "Duplicates removed: $REMOVED"
        
        if [[ "$REMOVED" -gt 0 ]]; then
            log_pass "Deduplication working (removed $REMOVED)"
        else
            log_info "No duplicates found in results (ok if dataset has no dups)"
        fi
    else
        log_fail "Enhancement metadata missing"
    fi
else
    log_fail "Deduplicate search failed"
fi
echo ""

# Test 3: Smart date filter
log_test "3. Smart Date Filter"
RESPONSE=$(curl -sf "$API_URL/search?q_text=report+dal+2021+in+poi&top_k=10&smart_filter=true" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Smart filter parameter accepted"
    
    # Check date filter recognition
    if echo "$RESPONSE" | jq -e '.enhancement.date_filter' > /dev/null 2>&1; then
        FILTER_TYPE=$(echo "$RESPONSE" | jq -r '.enhancement.date_filter.type' 2>/dev/null)
        FILTER_YEAR=$(echo "$RESPONSE" | jq -r '.enhancement.date_filter.year' 2>/dev/null)
        log_pass "Date filter detected: type=$FILTER_TYPE, year=$FILTER_YEAR"
        
        # Check if filtering was applied
        if echo "$RESPONSE" | jq -e '.enhancement.filtered_by_date' > /dev/null 2>&1; then
            FILTERED=$(echo "$RESPONSE" | jq -r '.enhancement.filtered_by_date' 2>/dev/null)
            log_info "Documents filtered: $FILTERED"
        fi
    else
        log_fail "Date filter not detected in query"
    fi
else
    log_fail "Smart filter search failed"
fi
echo ""

# Test 4: Query cleaning (stopwords removal)
log_test "4. Query Cleaning (Stopwords)"
RESPONSE=$(curl -sf "$API_URL/search?q_text=il+piano+operativo+dal+2021&top_k=5" 2>&1)
if echo "$RESPONSE" | jq -e '.enhancement.cleaned_query' > /dev/null 2>&1; then
    ORIGINAL=$(echo "$RESPONSE" | jq -r '.enhancement.original_query // "N/A"' 2>/dev/null)
    CLEANED=$(echo "$RESPONSE" | jq -r '.enhancement.cleaned_query' 2>/dev/null)
    
    log_pass "Query cleaning active"
    log_info "Original: '$ORIGINAL'"
    log_info "Cleaned:  '$CLEANED'"
    
    # Verify stopwords removed (il, dal should be gone)
    if ! echo "$CLEANED" | grep -q '\bil\b\|dal'; then
        log_pass "Stopwords correctly removed"
    else
        log_fail "Stopwords still present in cleaned query"
    fi
else
    log_fail "Query cleaning not working"
fi
echo ""

# Test 5: Combined features
log_test "5. Combined Features (dedup + date filter)"
RESPONSE=$(curl -sf "$API_URL/search?q_text=documenti+dal+2020&deduplicate=true&smart_filter=true&top_k=15" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Combined features work"
    
    HAS_DATE_FILTER=$(echo "$RESPONSE" | jq -e '.enhancement.date_filter' > /dev/null 2>&1 && echo "yes" || echo "no")
    HAS_DEDUP=$(echo "$RESPONSE" | jq -e '.enhancement.removed_duplicates' > /dev/null 2>&1 && echo "yes" || echo "no")
    
    log_info "Date filter: $HAS_DATE_FILTER"
    log_info "Deduplication: $HAS_DEDUP"
    
    if [[ "$HAS_DATE_FILTER" == "yes" ]] && [[ "$HAS_DEDUP" == "yes" ]]; then
        log_pass "Both enhancements active"
    fi
else
    log_fail "Combined features test failed"
fi
echo ""

# Test 6: Edge cases
log_test "6. Edge Cases"

# Empty query
log_info "Testing empty query..."
RESPONSE=$(curl -sf "$API_URL/search?q_text=&top_k=5" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Empty query handled"
else
    log_fail "Empty query not handled"
fi

# Query without date
log_info "Testing query without date pattern..."
RESPONSE=$(curl -sf "$API_URL/search?q_text=piano+operativo&deduplicate=true&top_k=5" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Non-date query handled"
    
    # Should not have date filter
    if ! echo "$RESPONSE" | jq -e '.enhancement.date_filter' > /dev/null 2>&1; then
        log_pass "No false positive date detection"
    else
        log_fail "False positive: date filter detected when it shouldn't"
    fi
fi

# Special characters
log_info "Testing special characters..."
RESPONSE=$(curl -sf "$API_URL/search?q_text=test+%26+prova&top_k=5" 2>&1)
if echo "$RESPONSE" | grep -q '"total"'; then
    log_pass "Special characters handled"
else
    log_fail "Special characters caused error"
fi

echo ""

# === PERFORMANCE TEST ===
log_test "7. Performance Test"

log_info "Testing search latency..."

# Normal search
START=$(date +%s%N)
curl -sf "$API_URL/search?q_text=test&top_k=20" > /dev/null 2>&1
END=$(date +%s%N)
NORMAL_MS=$(( (END - START) / 1000000 ))

# Enhanced search
START=$(date +%s%N)
curl -sf "$API_URL/search?q_text=test&deduplicate=true&smart_filter=true&top_k=20" > /dev/null 2>&1
END=$(date +%s%N)
ENHANCED_MS=$(( (END - START) / 1000000 ))

OVERHEAD=$(( ENHANCED_MS - NORMAL_MS ))

log_info "Normal search:   ${NORMAL_MS}ms"
log_info "Enhanced search: ${ENHANCED_MS}ms"
log_info "Overhead:        ${OVERHEAD}ms"

if [[ $OVERHEAD -lt 100 ]]; then
    log_pass "Performance acceptable (overhead <100ms)"
elif [[ $OVERHEAD -lt 200 ]]; then
    log_pass "Performance OK (overhead <200ms)"
else
    log_fail "Performance concern (overhead ${OVERHEAD}ms)"
fi

echo ""

# === MODULE IMPORT TEST ===
log_test "8. Module Import Test"

# Check if module can be imported in container
if docker exec kbsearch-api-1 python3 -c "import improve_search; print('OK')" 2>&1 | grep -q "OK"; then
    log_pass "Module importable in container"
else
    log_fail "Module import failed in container"
fi

# Check if functions are available
if docker exec kbsearch-api-1 python3 -c "from improve_search import enhance_search_query, extract_date_filter, deduplicate_results; print('OK')" 2>&1 | grep -q "OK"; then
    log_pass "All functions importable"
else
    log_fail "Function imports failed"
fi

echo ""

# === SUMMARY ===
echo "================================================================"
echo "  TEST SUMMARY"
echo "================================================================"
echo ""

TOTAL=$((PASSED + FAILED))
PASS_RATE=0
if [[ $TOTAL -gt 0 ]]; then
    PASS_RATE=$(( (PASSED * 100) / TOTAL ))
fi

echo -e "Total tests:  $TOTAL"
echo -e "${GREEN}Passed:       $PASSED${NC}"
echo -e "${RED}Failed:       $FAILED${NC}"
echo -e "Pass rate:    $PASS_RATE%"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}✅✅✅ ALL TESTS PASSED!${NC}"
    echo ""
    log_info "Improved search module working correctly"
    log_info "Features available:"
    echo "  - ✓ Version deduplication"
    echo "  - ✓ Smart date filtering"
    echo "  - ✓ Stopwords removal"
    echo "  - ✓ Backward compatible"
    echo ""
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo ""
    log_info "Check errors above and:"
    echo "  1. Review main.py integration"
    echo "  2. Check API logs: docker compose logs api --tail=100"
    echo "  3. Verify improve_search.py in container"
    echo ""
    exit 1
fi
