package repository

import "testing"

func TestSeedProductsReferenceExistingTags(t *testing.T) {
	tags, err := LoadProductTagData()
	if err != nil {
		t.Fatal(err)
	}
	products, err := LoadProductData()
	if err != nil {
		t.Fatal(err)
	}
	if len(tags) == 0 || len(products) == 0 {
		t.Fatal("empty catalog seed")
	}
	known := map[string]bool{}
	for _, tag := range tags {
		known[tag.Name] = true
	}
	seen := map[string]bool{}
	for _, product := range products {
		if product.ID == "" || seen[product.ID] {
			t.Fatalf("invalid/duplicate product: %s", product.ID)
		}
		seen[product.ID] = true
		if product.Name == "" || product.Price < 0 {
			t.Fatalf("invalid product: %+v", product)
		}
		for _, tag := range product.Tags {
			if !known[tag] {
				t.Fatalf("unknown tag %s for %s", tag, product.ID)
			}
		}
	}
}
