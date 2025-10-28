#!/bin/bash
API="http://localhost:8000"

echo "🧪 TEST IMPROVED SEARCH"
echo "======================="
echo ""

# Test 1: Deduplicazione
echo "1️⃣ DEDUPLICAZIONE"
curl -s "$API/search?q_text=piano&deduplicate=true&top_k=20" \
  | jq -r '"   Removed: " + (.enhancement.removed_duplicates | tostring) + " duplicates"'
echo ""

# Test 2: Filtro "dal YYYY"
echo "2️⃣ FILTRO 'dal 2021 in poi'"
curl -s "$API/search?q_text=documenti+dal+2021+in+poi&smart_filter=true" \
  | jq -r '"   Filter: " + (.enhancement.date_filter | tostring)'
echo ""

# Test 3: Filtro "dopo il YYYY"
echo "3️⃣ FILTRO 'dopo il 2022'"
curl -s "$API/search?q_text=offerte+dopo+il+2022&smart_filter=true" \
  | jq -r '"   Filter: " + (.enhancement.date_filter | tostring)'
echo ""

# Test 4: Range
echo "4️⃣ FILTRO 'tra 2020 e 2023'"
curl -s "$API/search?q_text=progetti+tra+2020+e+2023&smart_filter=true" \
  | jq -r '"   Filter: " + (.enhancement.date_filter | tostring)'
echo ""

# Test 5: Combinato
echo "5️⃣ COMBINATO (dedup + filter)"
RESULT=$(curl -s "$API/search?q_text=offerta+finale+dal+2021&deduplicate=true&smart_filter=true&top_k=20")
echo "   Total: $(echo $RESULT | jq '.total')"
echo "   Removed: $(echo $RESULT | jq '.enhancement.removed_duplicates') duplicates"
echo "   Filter: $(echo $RESULT | jq '.enhancement.date_filter')"
echo ""

echo "✅ Test completati!"
