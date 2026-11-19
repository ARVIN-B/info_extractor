# MCP platform response samples

Captured on 2026-11-19 from the installed MCP packages in this project's `.venv`. These are small live probes for understanding schema and response keys, not a claim of full provider coverage.

> Privacy and fidelity: phone numbers and email addresses are masked; values under account-like keys are redacted. IDs are replaced where the capture helper anonymized them. The report is UTF-8. The Windows terminal rendered some Persian text incorrectly during inspection; values visibly corrupted in the captured payload are marked, while readable UTF-8 values and all JSON keys/nesting are retained.

## Source summary

| Source | Live schema | Live search | Live detail | Notes |
|---|---|---|---|---|
| neshan | ok | ok | ok | Search and place detail returned; phone-like fields appeared in the response, values masked. |
| balad | ok | ok | ok | Search and place detail returned; phone-like fields appeared in the response, values masked. |
| emalls | ok | ok | ok | Product search, offers, and shop profile returned; profile includes an explicit `phone` key. |
| basalam | ok | ok | ok | Product search and vendor profile returned; this sample did not prove a public vendor phone field. |
| rasmio | ok | ok | not called / unavailable | Company search returned. `rs_company` was not called because this guest MCP account has a limited profile quota. |
| torob | ok | not verified | not called / unavailable | Schema returned. The one live `tb_find_shops` probe timed out at the server's 15-second limit; no retry was made. |
| iran_jobs | ok | ok | not called / unavailable | `job_companies` returned its three site sections; no separate company detail tool exists in the live schema. |
| quera | ok | ok | ok | Company search and company profile returned; this sample profile had no phone key. |
| digikala | ok | ok | ok | Product search and product detail returned, including seller/offer structures; public shop phone is not guaranteed. |
| snappshop | ok | ok | ok | Product search and product detail returned, including offers; public shop phone is not guaranteed. |

## Live tool schemas

The following is the actual installed server schema as returned by MCP `list_tools()`. Descriptions whose Persian text arrived corrupted are labeled; tool names, fields, types, defaults, bounds, enums, and required arrays are retained.

### neshan

```json
{
  "ns_search": {
    "properties": {
      "query": {
        "description": "Place name, category, street or square, Persian or English, e.g. 'کافه لمیز', 'پمپ بنزین', 'میدان ونک'.",
        "type": "string"
      },
      "near": {
        "default": "Tehran",
        "description": "City name ('Tehran', 'شیراز') or point 'lat,lng' to rank results by closeness to.",
        "type": "string"
      },
      "open_now": {
        "default": false,
        "description": "Only places open now (24-hour included).",
        "type": "boolean"
      },
      "min_rating": {
        "anyOf": [
          {
            "maximum": 5,
            "minimum": 1,
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Only places rated at least this (1-5)."
      },
      "limit": {
        "default": 10,
        "description": "Max results (1-30).",
        "maximum": 30,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "ns_place": {
    "properties": {
      "place_id": {
        "description": "Place `id` from ns_search (32 hex chars), or a neshan.org/maps/places/... link.",
        "type": "string"
      }
    },
    "required": [
      "place_id"
    ],
    "type": "object"
  }
}
```

### balad

```json
{
  "bl_search": {
    "properties": {
      "query": {
        "description": "Place name, street, address, neighbourhood or city, e.g. برج میلاد.",
        "maxLength": 200,
        "minLength": 1,
        "type": "string"
      },
      "lat": {
        "anyOf": [
          {
            "maximum": 40.5,
            "minimum": 24,
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Latitude to search around. Default: Tehran."
      },
      "lng": {
        "anyOf": [
          {
            "maximum": 64,
            "minimum": 43,
            "type": "number"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Longitude to search around. Default: Tehran."
      },
      "limit": {
        "default": 10,
        "description": "Max results (1-20).",
        "maximum": 20,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "bl_nearby": {
    "properties": {
      "what": {
        "description": "Category slug from bl_categories (e.g. pharmacy, gas-station) or free text (e.g. پیتزا).",
        "maxLength": 100,
        "minLength": 1,
        "type": "string"
      },
      "lat": {
        "description": "Latitude, e.g. 35.7448.",
        "maximum": 40.5,
        "minimum": 24,
        "type": "number"
      },
      "lng": {
        "description": "Longitude, e.g. 51.3753.",
        "maximum": 64,
        "minimum": 43,
        "type": "number"
      },
      "radius_km": {
        "default": 1,
        "description": "Box half-width in km (0.2-20).",
        "maximum": 20,
        "minimum": 0.2,
        "type": "number"
      },
      "limit": {
        "default": 10,
        "description": "Max places (1-40).",
        "maximum": 40,
        "minimum": 1,
        "type": "integer"
      },
      "open_now": {
        "default": false,
        "description": "Only places open now.",
        "type": "boolean"
      },
      "min_rating": {
        "anyOf": [
          {
            "enum": [
              "3",
              "4",
              "4.5"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Only places rated above this."
      },
      "sort": {
        "default": "relevance",
        "description": "rating = best first, popular = most visited.",
        "enum": [
          "relevance",
          "rating",
          "popular"
        ],
        "type": "string"
      },
      "with_phone": {
        "default": false,
        "description": "Only places with a phone number.",
        "type": "boolean"
      },
      "with_photos": {
        "default": false,
        "description": "Only places with photos.",
        "type": "boolean"
      },
      "price": {
        "anyOf": [
          {
            "enum": [
              "cheap",
              "moderate",
              "expensive"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Restaurants and cafes only."
      }
    },
    "required": [
      "what",
      "lat",
      "lng"
    ],
    "type": "object"
  },
  "bl_place": {
    "properties": {
      "id": {
        "description": "Place id from bl_search or bl_nearby.",
        "pattern": "^[A-Za-z0-9]{6,32}$",
        "type": "string"
      },
      "reviews": {
        "default": 3,
        "description": "Recent reviews to include (0-10).",
        "maximum": 10,
        "minimum": 0,
        "type": "integer"
      },
      "photos": {
        "default": 3,
        "description": "Photo URLs to include (0-20).",
        "maximum": 20,
        "minimum": 0,
        "type": "integer"
      }
    },
    "required": [
      "id"
    ],
    "type": "object"
  }
}
```

### emalls

```json
{
  "em_search": {
    "properties": {
      "query": {
        "default": "",
        "description": "Product words, Persian or English, e.g. گوشی سامسونگ A17. Empty with category_id browses it.",
        "maxLength": 200,
        "type": "string"
      },
      "category_id": {
        "anyOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Category id from em_categories, e.g. 39 phones."
      },
      "min_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Toman."
      },
      "max_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Toman."
      },
      "sort": {
        "default": "popular",
        "description": "cheapest also lists accessories: pair with min_price or category_id.",
        "enum": [
          "popular",
          "cheapest",
          "expensive",
          "newest"
        ],
        "type": "string"
      },
      "in_stock": {
        "default": true,
        "description": "Only products some shop has in stock.",
        "type": "boolean"
      },
      "page": {
        "default": 1,
        "description": "40 products per page.",
        "maximum": 50,
        "minimum": 1,
        "type": "integer"
      },
      "limit": {
        "default": 20,
        "description": "Max products from the page.",
        "maximum": 40,
        "minimum": 1,
        "type": "integer"
      },
      "brand_id": {
        "anyOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Brand id from em_filters."
      },
      "attributes": {
        "anyOf": [
          {
            "items": {
              "type": "integer"
            },
            "maxItems": 10,
            "type": "array"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Option ids from em_filters; one per spec group, all must match."
      }
    },
    "type": "object"
  },
  "em_offers": {
    "properties": {
      "product_id": {
        "description": "Product id from em_search.",
        "maximum": 2000000000,
        "minimum": 1,
        "type": "integer"
      },
      "city": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "City or province in Persian, e.g. تهران."
      },
      "established_only": {
        "default": false,
        "description": "Only established shops (با‌سابقه).",
        "type": "boolean"
      },
      "pickup_only": {
        "default": false,
        "description": "Only shops offering in-person purchase (خرید حضوری).",
        "type": "boolean"
      },
      "sort": {
        "default": "price",
        "description": "price: cheapest first; rating: best shops first.",
        "enum": [
          "price",
          "rating"
        ],
        "type": "string"
      },
      "limit": {
        "default": 10,
        "description": "Max offers.",
        "maximum": 50,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "product_id"
    ],
    "type": "object"
  },
  "em_shops": {
    "properties": {
      "query": {
        "description": "Part of a shop name, e.g. دیجی.",
        "maxLength": 100,
        "minLength": 1,
        "type": "string"
      },
      "page": {
        "default": 1,
        "description": "48 shops per page.",
        "maximum": 50,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "em_shop": {
    "properties": {
      "shop_id": {
        "description": "Shop id from em_offers or em_shops.",
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "reviews": {
        "default": 0,
        "description": "Newest customer reviews to add (0 = none).",
        "maximum": 20,
        "minimum": 0,
        "type": "integer"
      }
    },
    "required": [
      "shop_id"
    ],
    "type": "object"
  }
}
```

### basalam

```json
{
  "bs_search": {
    "properties": {
      "query": {
        "description": "Persian words, e.g. 'عسل طبیعی'.",
        "minLength": 1,
        "pattern": "\\S",
        "type": "string"
      },
      "sort": {
        "default": "relevance",
        "description": "Order.",
        "enum": [
          "relevance",
          "bestselling",
          "cheapest",
          "expensive",
          "newest"
        ],
        "type": "string"
      },
      "min_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Toman, e.g. 100000."
      },
      "max_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Toman, e.g. 500000."
      },
      "category_id": {
        "anyOf": [
          {
            "minimum": 1,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Id from bs_categories, any level."
      },
      "free_shipping": {
        "default": false,
        "description": "Only free shipping.",
        "type": "boolean"
      },
      "has_discount": {
        "default": false,
        "description": "Only discounted.",
        "type": "boolean"
      },
      "top_vendors": {
        "default": false,
        "description": "Only top-rated shops.",
        "type": "boolean"
      },
      "installments": {
        "default": false,
        "description": "Only installment-payable.",
        "type": "boolean"
      },
      "page": {
        "default": 1,
        "description": "Page number, 1-based.",
        "maximum": 200,
        "minimum": 1,
        "type": "integer"
      },
      "limit": {
        "default": 12,
        "description": "Products per page.",
        "maximum": 30,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "bs_vendor": {
    "properties": {
      "vendor": {
        "description": "shop_id from results, e.g. 'asalhowraman98'.",
        "minLength": 2,
        "type": "string"
      }
    },
    "required": [
      "vendor"
    ],
    "type": "object"
  }
}
```

### rasmio

```json
{
  "rs_search_companies": {
    "properties": {
      "query": {
        "default": "",
        "description": "Persian name, brand or activity words, e.g. 'دیجی کالا'. Empty = filters only.",
        "type": "string"
      },
      "province": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Persian province name, e.g. 'تهران'."
      },
      "city": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Persian city name, e.g. 'مشهد'."
      },
      "status": {
        "anyOf": [
          {
            "enum": [
              "active",
              "tax_inactive",
              "liquidated",
              "incomplete_data",
              "revoked",
              "license_ended",
              "inactive"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null
      },
      "company_type": {
        "anyOf": [
          {
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Legal form id (rs_options 'company_types'); 5 = سهامی خاص, 6 = با مسئولیت محدود, 3 = تعاونی."
      },
      "size": {
        "anyOf": [
          {
            "enum": [
              "xs",
              "s",
              "m",
              "l",
              "xl"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Headcount class, xs smallest .. xl largest."
      },
      "min_capital": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Minimum capital, Rial."
      },
      "max_capital": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Maximum capital, Rial."
      },
      "founded_after": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Registered on/after; '1400/01/01' or '2021-03-21'."
      },
      "founded_before": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Registered on/before, same formats."
      },
      "license_id": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "License id from rs_options('licenses')."
      },
      "product_category": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Product category slug (rs_options 'categories' or a product's category_slug)."
      },
      "has_brand": {
        "default": false,
        "description": "Owns a trademark.",
        "type": "boolean"
      },
      "has_subsidiary": {
        "default": false,
        "description": "Has subsidiaries.",
        "type": "boolean"
      },
      "has_contract": {
        "default": false,
        "description": "Has government contracts.",
        "type": "boolean"
      },
      "sort": {
        "default": "relevance",
        "enum": [
          "relevance",
          "most_viewed",
          "newest",
          "oldest",
          "lowest_capital",
          "highest_capital"
        ],
        "type": "string"
      },
      "page": {
        "default": 1,
        "maximum": 200,
        "minimum": 1,
        "type": "integer"
      },
      "page_size": {
        "default": 20,
        "maximum": 60,
        "minimum": 1,
        "type": "integer"
      }
    },
    "type": "object"
  },
  "rs_company": {
    "properties": {
      "company_id": {
        "description": "11-digit national id (شناسه ملی) from rs_search_companies, e.g. '10100360794'.",
        "type": "string"
      },
      "sections": {
        "anyOf": [
          {
            "items": {
              "enum": [
                "people",
                "ownership",
                "licenses",
                "finance",
                "ads"
              ],
              "type": "string"
            },
            "type": "array"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Parts besides the basics; empty = all."
      },
      "max_rows": {
        "default": 10,
        "description": "Rows per table.",
        "maximum": 30,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "company_id"
    ],
    "type": "object"
  }
}
```

### torob

```json
{
  "tb_find_shops": {
    "properties": {
      "query": {
        "description": "Shop name or domain, e.g. 'bavanmobile.ir'.",
        "maxLength": 80,
        "minLength": 1,
        "type": "string"
      },
      "city": {
        "anyOf": [
          {
            "maxLength": 40,
            "minLength": 1,
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "City or province, Persian."
      },
      "kind": {
        "default": "all",
        "description": "offline = in-person.",
        "enum": [
          "all",
          "online",
          "offline"
        ],
        "type": "string"
      },
      "page": {
        "default": 0,
        "maximum": 50,
        "minimum": 0,
        "type": "integer"
      },
      "limit": {
        "default": 10,
        "maximum": 30,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  }
}
```

### iran_jobs

```json
{
  "job_companies": {
    "properties": {
      "name": {
        "anyOf": [
          {
            "maxLength": 60,
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Company name, e.g. snapp."
      },
      "site": {
        "default": "all",
        "description": "all (three side by side) or one site.",
        "enum": [
          "all",
          "irantalent",
          "jobinja",
          "jobvision"
        ],
        "type": "string"
      },
      "page": {
        "default": 1,
        "description": "Page, 1-based, per site.",
        "maximum": 500,
        "minimum": 1,
        "type": "integer"
      }
    },
    "type": "object"
  }
}
```

### quera

```json
{
  "qr_companies": {
    "properties": {
      "search": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Company name, Persian or English."
      },
      "industry": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Industry id from qr_job_filters."
      },
      "city": {
        "anyOf": [
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "City name or id, as for qr_jobs."
      },
      "technologies": {
        "anyOf": [
          {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          {
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Tech codes, e.g. 'python'."
      },
      "size": {
        "anyOf": [
          {
            "enum": [
              "1-10",
              "11-50",
              "51-200",
              "201-500",
              "501-1000",
              "1001-5000",
              "5001-10000",
              "10000+"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Employee count range."
      },
      "page": {
        "default": 1,
        "description": "Page number, from 1.",
        "maximum": 100,
        "minimum": 1,
        "type": "integer"
      }
    },
    "type": "object"
  },
  "qr_company": {
    "properties": {
      "slug": {
        "description": "Company slug, e.g. 'kaya'.",
        "type": "string"
      }
    },
    "required": [
      "slug"
    ],
    "type": "object"
  }
}
```

### digikala

```json
{
  "dk_search": {
    "properties": {
      "query": {
        "description": "Persian or English words, e.g. 'گوشی سامسونگ'.",
        "maxLength": 100,
        "minLength": 2,
        "type": "string"
      },
      "sort": {
        "default": "relevance",
        "enum": [
          "relevance",
          "cheapest",
          "most_expensive",
          "best_selling",
          "most_viewed",
          "newest",
          "fastest_delivery",
          "buyers_pick"
        ],
        "type": "string"
      },
      "min_price": {
        "default": null,
        "minimum": 0,
        "type": [
          "integer",
          "null"
        ]
      },
      "max_price": {
        "default": null,
        "minimum": 0,
        "type": [
          "integer",
          "null"
        ]
      },
      "brand_ids": {
        "default": null,
        "description": "Brand ids (dk_product brand_id), e.g. [18] Samsung.",
        "items": {
          "type": "integer"
        },
        "maxItems": 5,
        "type": [
          "array",
          "null"
        ]
      },
      "attributes": {
        "default": null,
        "description": "{attribute id: [value ids]} from dk_filters, e.g. {2226: [19239]}. Values OR, attributes AND.",
        "additionalProperties": {
          "items": {
            "type": "integer"
          },
          "maxItems": 20,
          "type": "array"
        },
        "maxProperties": 10,
        "type": [
          "object",
          "null"
        ]
      },
      "colors": {
        "default": null,
        "description": "Color ids from dk_filters.",
        "items": {
          "type": "integer"
        },
        "maxItems": 10,
        "type": [
          "array",
          "null"
        ]
      },
      "seller_type": {
        "default": null,
        "enum": [
          "digikala",
          "official",
          "trusted",
          "roosta",
          null
        ],
        "type": [
          "string",
          "null"
        ]
      },
      "fast_delivery": {
        "default": false,
        "description": "Jet delivery only.",
        "type": "boolean"
      },
      "ready_to_ship": {
        "default": false,
        "description": "In Digikala's warehouse only.",
        "type": "boolean"
      },
      "in_stock_only": {
        "default": true,
        "type": "boolean"
      },
      "page": {
        "default": 1,
        "maximum": 100,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "dk_product": {
    "properties": {
      "product_id": {
        "maximum": 1000000000,
        "minimum": 1,
        "type": "integer"
      },
      "max_offers": {
        "default": 15,
        "maximum": 50,
        "minimum": 1,
        "type": "integer"
      },
      "include_specs": {
        "default": true,
        "type": "boolean"
      }
    },
    "required": [
      "product_id"
    ],
    "type": "object"
  }
}
```

### snappshop

```json
{
  "ss_search": {
    "properties": {
      "query": {
        "description": "Persian or English, e.g. 'هدفون بلوتوثی'.",
        "minLength": 1,
        "type": "string"
      },
      "sort": {
        "anyOf": [
          {
            "enum": [
              "popular",
              "cheapest",
              "priciest",
              "buyers_pick",
              "bestselling",
              "biggest_discount"
            ],
            "type": "string"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "List order; default is the site's relevance order."
      },
      "min_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Lowest price in Toman (not Rial)."
      },
      "max_price": {
        "anyOf": [
          {
            "minimum": 0,
            "type": "integer"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Highest price in Toman (not Rial)."
      },
      "brands": {
        "anyOf": [
          {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Brand ids from `brands` of an earlier answer."
      },
      "in_stock": {
        "default": false,
        "description": "Only products that can be bought now.",
        "type": "boolean"
      },
      "discounted": {
        "default": false,
        "description": "Only products with a discount.",
        "type": "boolean"
      },
      "express": {
        "default": false,
        "description": "Only products with fast delivery.",
        "type": "boolean"
      },
      "specs": {
        "anyOf": [
          {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "'filter=option' (name or id, from ss_filters), e.g. ['حافظه داخلی=256 گیگابایت']. One option per filter."
      },
      "colors": {
        "anyOf": [
          {
            "items": {
              "type": "string"
            },
            "type": "array"
          },
          {
            "type": "null"
          }
        ],
        "default": null,
        "description": "Colour names or ids from ss_filters."
      },
      "page": {
        "default": 1,
        "description": "12 items per page.",
        "maximum": 500,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "query"
    ],
    "type": "object"
  },
  "ss_product": {
    "properties": {
      "product": {
        "description": "`product_id` (digits), 'snp-<digits>' or a product URL.",
        "type": "string"
      }
    },
    "required": [
      "product"
    ],
    "type": "object"
  }
}
```

## Representative live responses

Each request and its complete captured response is shown below after privacy masking. Arrays retain the captured contents; the request limits were deliberately small where the tool supports a limit.

### neshan

#### `ns_search`

Request:

```json
{
  "query": "restaurant",
  "near": "isfahan",
  "limit": 1
}
```

Response:

```json
{
  "count": 1,
  "results": [
    {
      "id": "ID_001",
      "name": "شرکت تعاونی اتحادیه رستوران داران",
      "category": "بازار و مرکز خرید",
      "address": "ولی عصر، جعفریان (محله احمدآباد)",
      "lat": 32.6658,
      "lng": 51.6978,
      "distance_m": 3055,
      "rating": 5.0,
      "votes": 1,
      "status": "بسته است",
      "phone": "[PHONE_VALUE_MASKED]"
    }
  ]
}
```

#### `ns_place`

Request:

```json
{
  "place_id": "ID_001"
}
```

Response:

```json
{
  "id": "ID_001",
  "name": "شرکت تعاونی اتحادیه رستوران داران",
  "category": "بازار و مرکز خرید",
  "address": "اصفهان، ولی عصر، جعفریان (محله‌ی احمدآباد)",
  "lat": 32.6658,
  "lng": 51.6978,
  "rating": 5.0,
  "votes": 1,
  "open": "بسته است",
  "hours_today": "8 تا 14",
  "hours": [
    "پنجشنبه: 8 تا 14",
    "جمعه: تعطیل",
    "شنبه: 8 تا 17",
    "یکشنبه: 8 تا 17",
    "دوشنبه: 8 تا 17",
    "سه‌شنبه: 8 تا 17",
    "چهارشنبه: 8 تا 17"
  ],
  "phones": [
    "[PHONE_VALUE_MASKED]"
  ],
  "website": null,
  "photos": [],
  "photo_categories": null,
  "url": "https://neshan.org/maps/places/c675bfbbc85ed14daf070aa1a02f967a"
}
```

### balad

#### `bl_search`

Request:

```json
{
  "query": "restaurant in Isfahan",
  "lat": 32.6546,
  "lng": 51.668,
  "limit": 1
}
```

Response:

```json
{
  "results": [
    {
      "type": "poi",
      "name": "رستوران ترنج Toranj Restaurant",
      "id": "ID_002",
      "address": "مجلسی، بلوار ارم",
      "lat": 32.191871,
      "lng": 51.501082,
      "distance_km": 53.8
    }
  ]
}
```

#### `bl_place`

Request:

```json
{
  "id": "ID_002",
  "reviews": 0,
  "photos": 0
}
```

Response:

```json
{
  "id": "ID_002",
  "name": "رستوران ترنج Toranj Restaurant",
  "category": "رستوران",
  "lat": 32.191871,
  "lng": 51.501082,
  "hours": {
    "پنج‌شنبه": "8 صبح – 10 شب",
    "جمعه": "8 صبح – 10 شب",
    "شنبه": "8 صبح – 10 شب",
    "یکشنبه": "8 صبح – 10 شب",
    "دوشنبه": "8 صبح – 10 شب",
    "سه‌شنبه": "8 صبح – 10 شب",
    "چهارشنبه": "8 صبح – 10 شب"
  },
  "hours_status": "باز است",
  "address": "مجلسی، بلوار ارم بعد از چهار راه فجر",
  "phones": [
    "[PHONE_VALUE_MASKED]"
  ],
  "links": {
    "instagram": "https://instagram.com/Toranj__restoran"
  },
  "open_now": true,
  "rating": 5,
  "ratings": 4,
  "price": null,
  "menu": null,
  "amenities": [],
  "photo_count": 20,
  "photos": [],
  "stars_1_to_5": [
    0,
    0,
    0,
    0,
    4
  ],
  "review_count": 1,
  "reviews": [],
  "url": "https://balad.ir/p/رستوران-ترنج-majlesi_restaurant-6acFM8KFa2ALtz"
}
```

### emalls

#### `em_search`

Request:

```json
{
  "query": "Samsung smartphone",
  "page": 1,
  "limit": 1
}
```

Response:

```json
{
  "heading": "همه محصولات شامل samsung smartphone امروز (28 آبان)",
  "page": 1,
  "has_next": false,
  "count": 1,
  "products": [
    {
      "id": "ID_003",
      "title": "قلم لمسی اصلی گلکسی اس 23 اولترا سامسونگ Samsung S Pen Smartphone Stylus EJ-PS918 Galaxy S23 Ultra",
      "price": 8699000,
      "price_max": 12469677,
      "shops": 3,
      "updated": "2 سال و 6 ماه و 20 روز و 15 ساعت پیش"
    }
  ]
}
```

#### `em_offers`

Request:

```json
{
  "product_id": "ID_003",
  "city": ""
}
```

Response:

```json
{
  "product_id": "ID_003",
  "title": "قلم لمسی اصلی گلکسی اس 23 اولترا سامسونگ Samsung S Pen Smartphone Stylus EJ-PS918 Galaxy S23 Ultra",
  "total_shops": 3,
  "matching": 3,
  "offers": [
    {
      "shop": "درجیو",
      "shop_id": "ID_004",
      "city": "تهران",
      "province": "تهران",
      "price": 8699000,
      "rating": 5.0,
      "updated": "2 روز پیش",
      "established": true,
      "pickup": false,
      "in_stock": true,
      "buy_url": "https://click.emalls.ir/click?itemid=16654918&exid=463188665&shopType=1&sId=624120ff-14bb-6969-ac29-beb2341674b0&ts=1795098559&nonce=2E04001AB51B36D8EA25271DD7565879A44C98596B8514A700DAE8B348E6CD0F&sig=qkLq_aFtRFKYw1rdQW5YCdgNAwM48C5hN6P5AWA--z0"
    },
    {
      "shop": "دیجی کالا",
      "shop_id": "ID_005",
      "city": "تهران",
      "province": "تهران",
      "price": 9380000,
      "rating": 2.8,
      "updated": "3 روز پیش",
      "guarantee": "سرویس ویژه دیجی کالا: 7 روز تضمین بازگشت کالا",
      "established": true,
      "pickup": false,
      "in_stock": true,
      "buy_url": "https://click.emalls.ir/click?itemid=16654918&exid=220307599&shopType=1&sId=624120ff-14bb-6969-ac29-beb2341674b0&ts=1795098559&nonce=9F47D2E58CAE228D61D463973DEDA4B257BA15CEEF1DBA57021E4BD92D476521&sig=JaJelSyZDXSFLH7W39H4Pq78eHC-oR7EwlOLhnRnjc0"
    },
    {
      "shop": "کیان داریا ",
      "shop_id": "ID_006",
      "city": "تهران",
      "province": "تهران",
      "price": 12469677,
      "updated": "1 روز پیش",
      "established": true,
      "pickup": false,
      "in_stock": true,
      "buy_url": "https://click.emalls.ir/click?itemid=16654918&exid=422816036&shopType=1&sId=624120ff-14bb-6969-ac29-beb2341674b0&ts=1795098559&nonce=FAB7D5B7E80CB6222E743BFAF3841FC2C2ADA91DA6E0183882A8AE7EC7CA361C&sig=4gGFb-ieR5arDC5k5gfYNSLFMYcklAoPSuan1VM7iXQ"
    }
  ]
}
```

#### `em_shop`

Request:

```json
{
  "shop_id": "ID_004"
}
```

Response:

```json
{
  "id": "ID_004",
  "name": "درجیو",
  "rating": 5.0,
  "rating_votes": 1,
  "website": "https://dorjio.com/",
  "address": "تهران- خیابان دماوند - خیابان وحیدیه بن‌بست شهید بیژن برآهوئی پلاک 6 طبقه 1",
  "phone": "[PHONE_VALUE_MASKED]",
  "status": "در حال همکاری با ایمالز",
  "with_emalls": "4 سال و 11 ماه و 2 روز",
  "enamad": "دارد (یک ستاره)",
  "options": [
    "ارسال رایگان",
    "ارسال فوری",
    "ارسال با پیک",
    "ارسال با پست",
    "پرداخت آنلاین",
    "پرداخت کارت به کارت"
  ],
  "reviews": null
}
```

### basalam

#### `bs_search`

Request:

```json
{
  "query": "honey",
  "page": 1,
  "limit": 1
}
```

Response:

```json
{
  "total": 990,
  "page": 1,
  "products": [
    {
      "id": "ID_001",
      "name": "ماسک صورت ورقه ای پد پاک pad pak مدل عسل HONEY",
      "price": 25300,
      "rating": 4.6,
      "rating_count": 245,
      "in_stock": true,
      "stock": 292,
      "category": "ماسک صورت",
      "shop": "لوازم آرایشی تربچه",
      "shop_id": "ID_002"
    }
  ]
}
```

#### `bs_vendor`

Request:

```json
{
  "vendor": "atorobchebeautycom"
}
```

Response:

```json
{
  "id": "ID_003",
  "identifier": "atorobchebeautycom",
  "name": "لوازم آرایشی تربچه",
  "active": true,
  "status": "فعال",
  "created": "2021-12-22",
  "last_activity": "2026-11-19 13:21:09",
  "city": "قزوین",
  "province": "قزوین",
  "type": [
    "نا مشخص"
  ],
  "products": 261,
  "shipping": [
    "پست پیشتاز",
    "پست سفارشی",
    "پیک موتوری"
  ],
  "notice": null,
  "summary": "ما بصورت مستقیم محصولات آرایشی با کیفیت و اورجینال را تهیه میکنیم و به شما ارائه میدهیم\nهدف ما رساندن محصول بصورت مستقیم به مصرف کننده است",
  "url": "https://basalam.com/atorobchebeautycom"
}
```

### rasmio

#### `rs_search_companies`

Request:

```json
{
  "query": "technology company",
  "city": "",
  "province": "",
  "page": 1,
  "page_size": 1
}
```

Response:

```json
{
  "total": 10000,
  "page": 1,
  "pages": 10000,
  "results": [
    {
      "kind": "company",
      "company_id": "ID_007",
      "name": "PHARMA TRADE COMPANY C.F.Z",
      "summary": "9 سال • +1 میلیون ریال سرمایه ثبتی"
    }
  ]
}
```

### torob

The schema was captured, but the live `tb_find_shops` request timed out after 15 seconds. No response was captured and no repeat was made.

### iran_jobs

#### `job_companies`

Request:

```json
{
  "name": "snapp",
  "page": 1,
  "site": "all"
}
```

Response:

```json
{
  "irantalent": {
    "total": 11,
    "page": 1,
    "pages": 1,
    "companies": [
      {
        "id": "ID_008",
        "name": "Snapp Food",
        "name_fa": "اسنپ فود",
        "slug": "ID_009",
        "rating": 3.51,
        "ratings_count": 146,
        "open_jobs": 11,
        "url": "https://www.irantalent.com/company/snapp-food/67738998-a152-4039-aa7e-2da900edaa91/overview"
      },
      {
        "id": "ID_010",
        "name": "Snapp Group",
        "name_fa": "گروه اسنپ",
        "slug": "ID_011",
        "rating": 3.4,
        "ratings_count": 40,
        "open_jobs": 7,
        "url": "https://www.irantalent.com/company/snapp-group/a811a191-cd80-4b11-a3c9-f016961cbfec/overview"
      },
      {
        "id": "ID_012",
        "name": "Snapp",
        "name_fa": "اسنپ",
        "slug": "ID_013",
        "rating": 3.87,
        "ratings_count": 180,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp/ca8af3e1-023c-47c7-9750-ff7635f545bf/overview"
      },
      {
        "id": "ID_014",
        "name": "Snapp Box",
        "name_fa": "اسنپ باکس",
        "slug": "ID_015",
        "rating": 3.78,
        "ratings_count": 26,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-box/47fb3056-aeb2-4805-ac89-81f1dcbb89a3/overview"
      },
      {
        "id": "ID_016",
        "name": "SnappTrip",
        "name_fa": "آرا جهان نوین گستر اطلس",
        "slug": "ID_017",
        "rating": 3.33,
        "ratings_count": 36,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapptrip/edc5f498-8bca-43a5-b62f-0c059e96ad8d/overview"
      },
      {
        "id": "ID_018",
        "name": "SnappShop",
        "name_fa": "اسنپ شاپ",
        "slug": "ID_019",
        "rating": 3.36,
        "ratings_count": 29,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snappshop/9554a7c9-1dc3-4a6b-8a90-918088b06d21/overview"
      },
      {
        "id": "ID_020",
        "name": "Snapp Market",
        "name_fa": "اسنپ مارکت",
        "slug": "ID_021",
        "rating": 2.96,
        "ratings_count": 37,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-market/d92bb52e-30cf-4072-9d00-9b1db5b4c08c/overview"
      },
      {
        "id": "ID_022",
        "name": "Snapp Carfix",
        "name_fa": "اسنپ کارفیکس",
        "slug": "ID_023",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-carfix/d18d4fe8-783a-4766-af32-406533a939bc/overview"
      },
      {
        "id": "ID_024",
        "name": "Snapp Room",
        "name_fa": "اسنپ روم",
        "slug": "ID_025",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-room/34a96153-5ecd-4585-9e15-b78eb9d8953d/overview"
      },
      {
        "id": "ID_026",
        "name": "Snapp Doctor",
        "name_fa": "اسنپ دکتر",
        "slug": "ID_027",
        "ratings_count": 2,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-doctor/d8e1fc0f-27fa-4821-91ea-57c09279e17e/overview"
      },
      {
        "id": "ID_028",
        "name": "Snapp Market Pro",
        "name_fa": "اسنپ مارکت پرو",
        "slug": "ID_029",
        "ratings_count": 2,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/snapp-market-pro/e8928366-2534-4c63-a3d3-8eeb65fb3740/overview"
      }
    ]
  },
  "jobinja": {
    "page": 1,
    "companies": [
      {
        "slug": "ID_030",
        "name": "اسنپ پی",
        "name_en": "Snapp Pay",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_019",
        "name": "اسنپ شاپ",
        "name_en": "SnappShop",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_031",
        "name": "گروه اسنپ",
        "name_en": "Snapp Group",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_032",
        "name": "اسنپ مارکت",
        "name_en": "Snapp Market",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_033",
        "name": "اسنپ باکس",
        "name_en": "Snappbox",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_034",
        "name": "اسنپ فود",
        "name_en": "Snappfood",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_035",
        "name": "نوین مائده اطلس",
        "name_en": "Novin Maede Atlas (Snapp Kitchen)",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "ID_036",
        "name": "اسنپ تریپ",
        "name_en": "Snapp Trip",
        "city": "تهران، تهران",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      }
    ],
    "next": "Raise page for more."
  },
  "jobvision": {
    "total": 17,
    "page": 1,
    "companies": [
      {
        "id": "ID_037",
        "name": "اسنپ فود",
        "name_en": "snappfood",
        "open_ads": 88,
        "rating": 4.1,
        "rank": 87,
        "url": "https://jobvision.ir/companies/994"
      },
      {
        "id": "ID_038",
        "name": "اسنپ باکس",
        "name_en": "Snapp Box",
        "open_ads": 27,
        "rating": 3.98,
        "rank": 147,
        "url": "https://jobvision.ir/companies/152828"
      },
      {
        "id": "ID_039",
        "name": "اسنپ تریپ",
        "name_en": "SnappTrip",
        "open_ads": 5,
        "rating": 3.98,
        "rank": 148,
        "url": "https://jobvision.ir/companies/1274"
      },
      {
        "id": "ID_040",
        "name": "اسنپ پی",
        "name_en": "Snapp Pay",
        "open_ads": 55,
        "rating": 3.95,
        "rank": 169,
        "url": "https://jobvision.ir/companies/96834"
      },
      {
        "id": "ID_041",
        "name": "گروه اسنپ",
        "name_en": "Snapp Group",
        "open_ads": 56,
        "rating": 3.89,
        "rank": 219,
        "url": "https://jobvision.ir/companies/454"
      },
      {
        "id": "ID_042",
        "name": "اسنپ‌شاپ",
        "name_en": "SnappShop",
        "open_ads": 21,
        "rating": 3.79,
        "rank": 304,
        "url": "https://jobvision.ir/companies/21906"
      },
      {
        "id": "ID_043",
        "name": "اسنپ مارکت",
        "name_en": "SnappMarket",
        "open_ads": 73,
        "rating": 3.75,
        "rank": 346,
        "url": "https://jobvision.ir/companies/1895"
      },
      {
        "id": "ID_044",
        "name": "اسنپ ساپلای",
        "name_en": "Snapp Supply",
        "open_ads": 8,
        "rating": 3.72,
        "rank": 380,
        "url": "https://jobvision.ir/companies/214163"
      },
      {
        "id": "ID_045",
        "name": "اسنپ",
        "name_en": "Snapp",
        "open_ads": 33,
        "rating": 3.47,
        "rank": 590,
        "url": "https://jobvision.ir/companies/280"
      },
      {
        "id": "ID_046",
        "name": "اسنپ روم",
        "name_en": "Snapp Room",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/6974"
      }
    ]
  }
}
```

### quera

#### `qr_companies`

Request:

```json
{
  "search": "snapp",
  "city": null,
  "page": 1
}
```

Response:

```json
{
  "total": 13,
  "page": 1,
  "has_more": false,
  "results": [
    {
      "slug": "ID_013",
      "name": "اسنپ",
      "tagline": "اسنپ، منتظر شماست!",
      "city": "تهران",
      "size": "1001-5000",
      "open_jobs": 0,
      "technologies": [
        "Python",
        "Java",
        "PHP",
        "Android",
        "iOS",
        "MySQL",
        "React",
        "Swift",
        "Angular",
        "Docker"
      ],
      "url": "https://quera.org/magnet/companies/snapp"
    },
    {
      "slug": "ID_017",
      "name": "اسنپ‌تریپ",
      "tagline": "رزرو هتل و خرید بلیط هواپیما و اتوبوس",
      "city": "تهران",
      "size": "201-500",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "Java",
        "React",
        "Angular",
        "WordPress",
        "Scala"
      ],
      "url": "https://quera.org/magnet/companies/snapptrip"
    },
    {
      "slug": "ID_034",
      "name": "اسنپ فود",
      "tagline": "سفارش اینترنتی غذا",
      "city": "تهران",
      "size": "1001-5000",
      "open_jobs": 0,
      "technologies": [
        "PHP",
        "MySQL",
        "React",
        ".NET",
        "PostgreSQL",
        "Go"
      ],
      "url": "https://quera.org/magnet/companies/snappfood"
    },
    {
      "slug": "ID_047",
      "name": "اسنپ دکتر",
      "tagline": "دارو، مشاوره پزشکی آنلاین و آزمایش",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "PHP",
        "MySQL",
        "React",
        "Laravel",
        "MongoDB",
        "Git",
        "Docker",
        "Unit Testing",
        "Symfony",
        "Elasticsearch"
      ],
      "url": "https://quera.org/magnet/companies/snappdoctor"
    },
    {
      "slug": "ID_048",
      "name": "Snapp Kitchen",
      "tagline": "تو هم یه طعم تازه ببخش",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "React",
        "PostgreSQL",
        "Docker",
        "Go",
        "Kubernetes"
      ],
      "url": "https://quera.org/magnet/companies/snappfood-1"
    },
    {
      "slug": "ID_032",
      "name": "Snapp Market",
      "tagline": "خرید آنلاین از هایپرمارکت",
      "city": "تهران",
      "size": "201-500",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "PHP",
        "MySQL",
        "React",
        "Node.js",
        "Laravel",
        "React Native",
        "Express",
        "Symfony",
        "Elasticsearch"
      ],
      "url": "https://quera.org/magnet/companies/snappmarket"
    },
    {
      "slug": "ID_049",
      "name": "اسنپ ساپلای",
      "tagline": "سامانه تامین مواد اولیه اسنپ ساپلای",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "MySQL",
        "React",
        "Node.js",
        "Go"
      ],
      "url": "https://quera.org/magnet/companies/snappsupply"
    },
    {
      "slug": "ID_050",
      "name": "Snapp Group",
      "tagline": "تجارت الکترونیک",
      "city": "تهران",
      "size": "5001-10000",
      "open_jobs": 0,
      "technologies": [
        "PHP",
        "Laravel"
      ],
      "url": "https://quera.org/magnet/companies/snappgroup"
    },
    {
      "slug": "ID_051",
      "name": "اسنپ کارفیکس",
      "tagline": "خدمات خودرویی آنلاین",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "Python",
        "MySQL",
        "React",
        "Django",
        "Docker",
        "Celery"
      ],
      "url": "https://quera.org/magnet/companies/snappcarfix"
    },
    {
      "slug": "ID_019",
      "name": "اسنپ شاپ",
      "tagline": "اسنپ شاپ",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "Python",
        "PHP",
        "React",
        "Django",
        "Laravel",
        "Go",
        "Symfony"
      ],
      "url": "https://quera.org/magnet/companies/snappshop"
    },
    {
      "slug": "ID_052",
      "name": "Snapp Room",
      "tagline": "ررزو اقامتگاه‌های اقتصادی",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "React"
      ],
      "url": "https://quera.org/magnet/companies/snapproom"
    },
    {
      "slug": "ID_053",
      "name": "SnappQ",
      "tagline": "اسنپ کیو - بازی آنلاین",
      "city": "تهران",
      "size": "11-50",
      "open_jobs": 0,
      "technologies": [
        "Android",
        "iOS",
        "React",
        "MongoDB",
        "Go"
      ],
      "url": "https://quera.org/magnet/companies/snapq"
    },
    {
      "slug": "ID_054",
      "name": "اسنپ گروسری",
      "tagline": "سرویس سریع سوپرمارکتی",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "PHP"
      ],
      "url": "https://quera.org/magnet/companies/snappexpress"
    }
  ]
}
```

#### `qr_company`

Request:

```json
{
  "slug": "ID_013"
}
```

Response:

```json
{
  "slug": "ID_013",
  "name": "اسنپ",
  "tagline": "اسنپ، منتظر شماست!",
  "industry": "اینترنت / تجارت الکترونیک / خدمات آنلاین",
  "size": "1001-5000",
  "founded_jalali_year": 1393,
  "city": "تهران",
  "address": "ولی عصر، زعفرانیه تقاطع مقدس اردبیلی و فلاحی پلاک 2",
  "website": "http://snapp.ir",
  "social": {
    "instagram": "https://www.instagram.com/snapp_team/",
    "linkedin": "https://www.linkedin.com/company/snapp.ir/",
    "twitter": "https://twitter.com/snapp_team",
    "telegram": "https://telegram.com/snapp_team"
  },
  "about": "",
  "statement": "Snapp is the pioneer provider of ride-hailing mobile solutions in Iran that connects smartphone owners in need of a ride to Snapp drivers who use their private cars offering transportation services. We are ambitious, passionate, engaged, and excited about pushing the boundaries of the transportation industry to new frontiers and be the first choice of each user in Iran.",
  "technologies": [
    "Python",
    "Java",
    "PHP",
    "Android",
    "iOS",
    "MySQL",
    "React",
    "Swift",
    "Angular",
    "Docker",
    "Vue.js",
    "Go",
    "Kubernetes",
    "Redis",
    "Cassandra",
    "OpenShift",
    "OpenStack",
    "Serverside JavaScript",
    "Ceph"
  ],
  "benefits": [
    "Flexible working hours",
    "Competitive salary",
    "Employee Loan",
    "A great culture of R&D",
    "Gaming Room",
    "Monthly Snapp credit",
    "Pizza-loving culture",
    "Supplementary health insurance",
    "Team Building",
    "On-Site Doctor",
    "Remote Work",
    "Gifts"
  ],
  "open_jobs": [],
  "url": "https://quera.org/magnet/companies/snapp"
}
```

### digikala

#### `dk_search`

Request:

```json
{
  "query": "Samsung phone",
  "page": 1
}
```

Response:

```json
{
  "total": 968,
  "page": 1,
  "total_pages": 49,
  "products": [
    {
      "id": "ID_004",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A36 دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 102816300,
      "price_before_discount": 105996100,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.4,
      "rating_count": 1532,
      "image": "https://dkstatics-public.digikala.com/digikala-products/6cd26d265db5b92dc3a8c1f24aeefe38f5474c08_1747563608.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-18577783/",
      "match": "all"
    },
    {
      "id": "ID_005",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A37 دو سیم‌کارت ظرفیت 256 گیگابایت و رم 12 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 133606800,
      "price_before_discount": 137739000,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.7,
      "rating_count": 61,
      "image": "https://dkstatics-public.digikala.com/digikala-products/c9333c454ed51246225feb64af5f5760a584a4ef_1790692105.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-21670153/",
      "match": "all"
    },
    {
      "id": "ID_006",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A36 دو سیم کارت ظرفیت 128 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 92538200,
      "price_before_discount": 95400200,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.6,
      "rating_count": 1037,
      "image": "https://dkstatics-public.digikala.com/digikala-products/87d4b5d7f12536a9a7365553e8808eef6b64b90e_1747563430.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-18577732/",
      "match": "all"
    },
    {
      "id": "ID_007",
      "title": "گوشی موبایل سامسونگ مدل Galaxy S25 FE دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 186846300,
      "price_before_discount": 192625000,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.6,
      "rating_count": 2517,
      "image": "https://dkstatics-public.digikala.com/digikala-products/55582a9ac4add1b88050b458e7d490564b3ac4b6_1759667022.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20135132/",
      "match": "all"
    },
    {
      "id": "ID_008",
      "title": "گوشی موبایل سامسونگ مدل Galaxy S26 Ultra دو سیم‌کارت ظرفیت 256 گیگابایت و رم 12 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 437999000,
      "in_stock": true,
      "seller": "پیدا تک",
      "rating": 4.7,
      "rating_count": 103,
      "image": "https://dkstatics-public.digikala.com/digikala-products/f763c68074bc2007562135176a588d2324593b63_1779812739.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-21462684/",
      "match": "all"
    },
    {
      "id": "ID_009",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A56 دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 127855700,
      "price_before_discount": 131809800,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.6,
      "rating_count": 3216,
      "image": "https://dkstatics-public.digikala.com/digikala-products/abb89918836e519343bdad17448cda4adeff4d4e_1746028045.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-18575915/",
      "match": "all"
    },
    {
      "id": "ID_010",
      "title": "تبلت سامسونگ مدل Galaxy Tab A7 Lite ظرفیت 32 گیگابایت و رم 3 گیگابایت",
      "brand": "سامسونگ",
      "price": 67900000,
      "in_stock": true,
      "seller": "دیزنیران",
      "rating": 4.2,
      "rating_count": 3616,
      "image": "https://dkstatics-public.digikala.com/digikala-products/fa5dd8061fc29f644c56f8de6fc32883b3efee17_1771425802.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-5549287/",
      "match": "some",
      "missing_words": [
        "phone"
      ]
    },
    {
      "id": "ID_011",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A07 دو سیم کارت ظرفیت 64 گیگابایت و رم 4 گیگابایت",
      "brand": "سامسونگ",
      "price": 39633200,
      "price_before_discount": 40859000,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.4,
      "rating_count": 2401,
      "image": "https://dkstatics-public.digikala.com/digikala-products/6e193ccbadf1dd14bc3f15df8050006e44c96846_1763385148.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20109389/",
      "match": "all"
    },
    {
      "id": "ID_012",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A56 دو سیم کارت ظرفیت 256 گیگابایت و رم 12 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 138376700,
      "price_before_discount": 142656400,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.5,
      "rating_count": 1088,
      "image": "https://dkstatics-public.digikala.com/digikala-products/36bc74a654bd32f152b13a2f8f283cf5bb71b370_1746028011.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-18575577/",
      "match": "all"
    },
    {
      "id": "ID_013",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A27 دو سیم کارت ظرفیت 128 گیگابایت و رم 6 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 85480200,
      "price_before_discount": 88123900,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.2,
      "rating_count": 66,
      "image": "https://dkstatics-public.digikala.com/digikala-products/d73e160b9102d622e8586db156c9fe854dec7c21_1790756257.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-22118543/",
      "match": "all"
    },
    {
      "id": "ID_014",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A17 4G دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 86799000,
      "in_stock": true,
      "seller": "سگالینو",
      "rating": 4.5,
      "rating_count": 833,
      "image": "https://dkstatics-public.digikala.com/digikala-products/eceb8bf074982af4e6d9bf72e2d7f77328074fd8_1765807107.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20490734/",
      "match": "all"
    },
    {
      "id": "ID_015",
      "title": "گوشی موبایل سامسونگ مدل Galaxy S25 Ultra دو سیم کارت ظرفیت 512 گیگابایت و رم 12 گیگابایت - پک ویتنام",
      "brand": "سامسونگ",
      "price": 519999000,
      "in_stock": true,
      "seller": "بهار کیهان ارتباطات",
      "rating": 4.6,
      "rating_count": 262,
      "image": "https://dkstatics-public.digikala.com/digikala-products/b898a97a346068c4f8e95cc9c7cfdf2b5f700e3f_1738145246.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-17918958/",
      "match": "all"
    },
    {
      "id": "ID_016",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A16 4G دو سیم کارت ظرفیت 128 گیگابایت و رم 6 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 79000000,
      "in_stock": true,
      "seller": " فناوری یاری آرتمیس",
      "rating": 4.5,
      "rating_count": 3373,
      "image": "https://dkstatics-public.digikala.com/digikala-products/b07e66e28603bd9655bce180fb46d4047412a3fa_1737985896.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-17464490/",
      "match": "all"
    },
    {
      "id": "ID_017",
      "title": "گوشی موبایل سامسونگ مدل Galaxy S25 Ultra دو سیم کارت ظرفیت 256 گیگابایت و رم 12 گیگابایت - پک ویتنام",
      "brand": "سامسونگ",
      "price": 382664900,
      "price_before_discount": 394499900,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.5,
      "rating_count": 1866,
      "image": "https://dkstatics-public.digikala.com/digikala-products/2342ad87776c9801a8116d41950cb5909bddc16b_1738145086.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-17918956/",
      "match": "all"
    },
    {
      "id": "ID_018",
      "title": "گوشی موبایل سامسونگ مدل S25 FE دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام - به همراه شارژر 45 وات سامسونگ",
      "brand": "سامسونگ",
      "price": 194330000,
      "in_stock": true,
      "seller": "پایاگستر شهر",
      "rating": 4.4,
      "rating_count": 212,
      "image": "https://dkstatics-public.digikala.com/digikala-products/95b2aeae56eaf62116a6b7ce162eaa04a9157309_1764666061.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20592831/",
      "match": "all"
    },
    {
      "id": "ID_019",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A17 4G دو سیم کارت ظرفیت 128 گیگابایت و رم 6 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 67604400,
      "price_before_discount": 69695300,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.4,
      "rating_count": 1396,
      "image": "https://dkstatics-public.digikala.com/digikala-products/68a4f680e47e209c5b090c5479004a3902342d07_1771839003.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20490714/",
      "match": "all"
    },
    {
      "id": "ID_020",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A07 دو سیم کارت ظرفیت 128گیگابایت و رم 6 گیگابایت ",
      "brand": "سامسونگ",
      "price": 58382800,
      "price_before_discount": 60188500,
      "discount_pct": 3,
      "in_stock": true,
      "seller": "دیجی‌کالا",
      "rating": 4.4,
      "rating_count": 1566,
      "image": "https://dkstatics-public.digikala.com/digikala-products/716bde6ae900692c549a7469ec685da70eca49f4_1763385560.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20110013/",
      "match": "all"
    },
    {
      "id": "ID_021",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A56 دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام - به همراه شارژر 25 وات سامسونگ",
      "brand": "سامسونگ",
      "price": 132505000,
      "in_stock": true,
      "seller": "سپاهان همراه یاقوت",
      "rating": 4.4,
      "rating_count": 363,
      "image": "https://dkstatics-public.digikala.com/digikala-products/c9d90d7462483d1d90075f79cdd71d9e7f34430a_1746028496.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-18909423/",
      "match": "all"
    },
    {
      "id": "ID_022",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A16 4G دو سیم کارت ظرفیت 128 گیگابایت و رم 4 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 59999000,
      "in_stock": true,
      "seller": "بهار کیهان ارتباطات",
      "rating": 4.5,
      "rating_count": 3617,
      "image": "https://dkstatics-public.digikala.com/digikala-products/b9036d74149f629611d958331c26541854c3d4f2_1763240650.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-17464125/",
      "match": "all"
    },
    {
      "id": "ID_023",
      "title": "گوشی موبایل سامسونگ مدل Galaxy A55 دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
      "brand": "سامسونگ",
      "price": 150000000,
      "in_stock": true,
      "seller": " فناوری یاری آرتمیس",
      "rating": 4.6,
      "rating_count": 5257,
      "image": "https://dkstatics-public.digikala.com/digikala-products/0a5e74229cb456ce6689a834c4ba1e566fc03937_1727520302.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-14851833/",
      "match": "all"
    }
  ],
  "matches": {
    "all": 19,
    "some": 1,
    "none": 0
  }
}
```

#### `dk_product`

Request:

```json
{
  "product_id": "ID_004"
}
```

Response:

```json
{
  "id": "ID_004",
  "title": "گوشی موبایل سامسونگ مدل Galaxy A36 دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت - ویتنام",
  "brand": "سامسونگ",
  "price": 102816300,
  "price_before_discount": 105996100,
  "discount_pct": 3.0,
  "in_stock": true,
  "seller": "دیجی‌کالا",
  "rating": 4.4,
  "rating_count": 1532,
  "image": "https://dkstatics-public.digikala.com/digikala-products/6cd26d265db5b92dc3a8c1f24aeefe38f5474c08_1747563608.jpg?x-oss-process=image/resize,m_lfit,h_800,w_800/quality,q_90",
  "url": "https://www.digikala.com/product/dkp-18577783/",
  "store": "digikala",
  "title_en": "Samsung Galaxy A36 Dual SIM Storage 256GB And 8GB RAM Mobile Phone - Vietnam",
  "brand_id": 18,
  "brand_code": "samsung",
  "category": {
    "id": "ID_024",
    "code": "mobile-phone",
    "title": "گوشی موبایل"
  },
  "lowest_price_30d": 91590003,
  "colors": [
    "سفید",
    "مشکی",
    "زرد لیمویی",
    "بنفش"
  ],
  "comments_count": 1051,
  "questions_count": 609,
  "offers_count": 26,
  "offers": [
    {
      "variant_id": 66236801,
      "variant": "سفید",
      "price": 102816300,
      "price_before_discount": 105996100,
      "discount_pct": 3.0,
      "stock_left": 1,
      "seller": "دیجی‌کالا",
      "seller_code": "ID_025",
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 65565830,
      "variant": "مشکی",
      "price": 102999100,
      "price_before_discount": 106184700,
      "discount_pct": 3.0,
      "seller": "دیجی‌کالا",
      "seller_code": "ID_025",
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 65588217,
      "variant": "مشکی",
      "price": 103974700,
      "price_before_discount": 107190400,
      "discount_pct": 3.0,
      "seller": "دیجی‌کالا",
      "seller_code": "ID_025",
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 66316180,
      "variant": "بنفش",
      "price": 104148700,
      "price_before_discount": 107369800,
      "discount_pct": 3.0,
      "seller": "دیجی‌کالا",
      "seller_code": "ID_025",
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 80919727,
      "variant": "زرد لیمویی",
      "price": 104202000,
      "stock_left": 1,
      "seller": "سپاهان همراه یاقوت",
      "seller_code": "ID_026",
      "seller_rating": 4.3,
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 68933756,
      "variant": "مشکی",
      "price": 104799000,
      "seller": "اسمارت تکنولوژی قشم",
      "seller_code": "ID_027",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 66268777,
      "variant": "مشکی",
      "price": 105005000,
      "stock_left": 1,
      "seller": "سپاهان همراه یاقوت",
      "seller_code": "ID_026",
      "seller_rating": 4.3,
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 75597549,
      "variant": "مشکی",
      "price": 105900000,
      "seller": "سگالینو",
      "seller_code": "ID_028",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 75527187,
      "variant": "سفید",
      "price": 105900000,
      "seller": "سگالینو",
      "seller_code": "ID_028",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 80914018,
      "variant": "مشکی",
      "price": 105900000,
      "stock_left": 1,
      "seller": "سگالینو",
      "seller_code": "ID_028",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 84745568,
      "variant": "مشکی",
      "price": 105999000,
      "stock_left": 1,
      "seller": "پیدا تک",
      "seller_code": "ID_029",
      "seller_rating": 4.2,
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار فروشنده",
      "ships_by": [
        "digikala"
      ],
      "free_shipping": false,
      "lead_time_days": 1
    },
    {
      "variant_id": 65588249,
      "variant": "بنفش",
      "price": 106312900,
      "price_before_discount": 109600900,
      "discount_pct": 3.0,
      "stock_left": 1,
      "seller": "دیجی‌کالا",
      "seller_code": "ID_025",
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 80381483,
      "variant": "سفید",
      "price": 106450000,
      "seller": "پایاگستر شهر",
      "seller_code": "ID_030",
      "seller_rating": 4.3,
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار فروشنده",
      "ships_by": [
        "digikala"
      ],
      "free_shipping": false,
      "lead_time_days": 1
    },
    {
      "variant_id": 73712881,
      "variant": "سفید",
      "price": 106999000,
      "stock_left": 3,
      "seller": "بهار کیهان ارتباطات",
      "seller_code": "ID_031",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه هماهنگ (داریا همراه)",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    },
    {
      "variant_id": 74526655,
      "variant": "مشکی",
      "price": 106999000,
      "stock_left": 2,
      "seller": "بهار کیهان ارتباطات",
      "seller_code": "ID_031",
      "seller_rating": 4.4,
      "warranty": "گارانتی 18 ماهه شرکتی",
      "shipping": "موجود در انبار دیجی‌کالا",
      "ships_by": [
        "digikala",
        "jet"
      ],
      "free_shipping": false,
      "lead_time_days": 0
    }
  ],
  "images": [
    "https://dkstatics-public.digikala.com/digikala-products/8651eff3abeb0eef2f94b01bb86cccb1f5c578cf_1755595756.jpg?x-oss-process=image/resize,m_lfit,h_800,w_800/quality,q_90",
    "https://dkstatics-public.digikala.com/digikala-products/77d461069e76c6216f9154b8d42ac81e0ce2b405_1755595756.jpg?x-oss-process=image/resize,m_lfit,h_800,w_800/quality,q_90",
    "https://dkstatics-public.digikala.com/digikala-products/d28f8d2cd5bf5c3725a9b37900e33b327a928ff3_1755431100.jpg?x-oss-process=image/resize,m_lfit,h_800,w_800/quality,q_90",
    "https://dkstatics-public.digikala.com/digikala-products/42718ce6ea7006d3b71284b090c70d6123395437_1741527697.jpg?x-oss-process=image/resize,m_lfit,h_800,w_800/quality,q_90"
  ],
  "specs": {
    "مشخصات کلی": {
      "نوع گوشی موبایل": "سیستم عامل اندروید",
      "دسته ‌بندی": "‌میان‌رده",
      "مدل": "Galaxy A36",
      "زمان معرفی": "2 مارس 2025",
      "ابعاد": "162.9x78.2x7.4 میلی‌متر",
      "وزن": "195 گرم",
      "توضیحات بدنه": "قاب جلو و پشت از جنس شیشه (Gorilla Glass Victus Plus) /\nفریم کناری از جنس پلاستیک",
      "قابلیت‌های مقاومتی": "مقاوم در برابر نفوذ آب, مقاوم در برابر نفوذ گرد و غبار",
      "تعداد سیم کارت": "دو عدد",
      "نوع سیم کارت": "سایز نانو (8.8 × 12.3 میلی‌متر)",
      "ویژگی‌های کلیدی": "مقاوم در برابر نفوذ آب (تا عمق 1 متری به مدت 30 دقیقه)"
    },
    "صفحه نمایش": {
      "فناوری صفحه‌ نمایش": "Super AMOLED",
      "نرخ به‌روزرسانی تصویر": "120 هرتز",
      "روشنایی صفحه نمایش": "1900 نیت",
      "اندازه": "6.7 اینچ",
      "نسبت صفحه‌ نمایش به بدنه": "86.5%",
      "نسبت تصویر": "19.5:9",
      "رزولوشن صفحه نمایش": "1080x2340 پیکسل",
      "تراکم پیکسلی": "385 پیکسل بر اینچ",
      "سایر قابلیت‌ها": "پشتیبانی از حالت صفحه نمایش همیشه روشن (Always on display)"
    },
    "پردازنده": {
      "تراشه": "Qualcomm SM6475-AB Snapdragon 6 Gen 3 (4 nm)",
      "پردازنده‌": "هشت هسته‌ای (چهار هسته 2.4 گیگاهرتزی از نوع Cortex-A78 - چهار هسته 1.8 گیگاهرتزی از نوع Cortex-A55)",
      "فرکانس پردازنده‌ مرکزی": "2.4 - 1.8 گیگاهرتز",
      "پردازنده‌ گرافیکی": "Adreno 710"
    },
    "حافظه": {
      "حافظه داخلی": "256 گیگابایت",
      "مقدار RAM": "8 گیگابایت",
      "پشتیبانی از کارت حافظه": "فاقد پشتیبانی از کارت حافظه"
    },
    "ارتباطات": {
      "شبکه‌های مخابراتی": "5G, 4G, 3G, 2G",
      "نسخه بلوتوث": "5.4",
      "مشخصات بلوتوث": "پشتیبانی از تکنولوژی A2DP و اتصال بهتر با سایز وسایل الکترونیکی / مجهز به تکنولوژی LE و مصرف بهینه باتری",
      "تکنولوژی‌های مکان‌یابی (GPS)": "GALILEO, GLONASS, BDS(Beidou), GPS",
      "رادیو": "فاقد پشتیبانی",
      "درگاه‌ها و فناوری‌های ارتباطی": "USB Type-C 2.0",
      "شبکه‌های ارتباطی قابل پشتیبانی": "بلوتوث, Wi-Fi, OTG"
    },
    "دوربین": {
      "تعداد دوربین‌های پشت گوشی": "3 ماژول دوربین",
      "نوع لنز دوربین اصلی": "عریض",
      "رزولوشن دوربین اصلی": "50 مگاپیکسل",
      "مشخصات دوربین اصلی": "مجهز به لرزشگیر اپتیکال - دریچه دیافراگم f/1.8 - سایز لنز 1/1.96 اینچ - امکان ثبت تصویر به صورت پانوراما - مجهز به فناوری HDR",
      "نوع لنز دوربین دوم": "فوق عریض",
      "رزولوشن دوربین دوم": "8 مگاپیکسل",
      "مشخصات دوربین دوم": "دریچه دیافراگم f/2.2 - سایز لنز 1/4.0 اینچ - قابلیت ثبت تصاویر با پیکسل‌هایی به اندازه 1.12 میکرومتر - زاویه دید 123 درجه",
      "نوع لنز دوربین سوم": "ماکرو",
      "رزولوشن دوربین سوم": "5 مگاپیکسل",
      "مشخصات دوربین سوم": "دریچه دیافراگم f/2.4",
      "فناوری فوکوس": "PDAF",
      "رزولوشن فیلمبرداری": "4K",
      "سایر مشخصات فیلمبرداری": "رزولوشن 4K با سرعت 30 فریم بر ثانیه / رزولوشن 1080p با سرعت 30 و 60 فریم بر ثانیه / مجهز به لرزشگیر تصویر ژیروسکوپی",
      "فلش": "LED",
      "رزولوشن دوربین سلفی": "12 مگاپیکسل",
      "مشخصات دوربین سلفی": "دریچه دیافراگم f/2.0 / امکان فیلمبرداری با رزولوشن 4K با سرعت 30 فریم بر ثانیه / رزولوشن 1080p با سرعت 30 فریم بر ثانیه - پشتیبانی از HDR10"
    },
    "صدا": {
      "اسپیکر": "استریو",
      "خروجی صدا": "USB Type-C"
    },
    "امکانات نرم افزاری": {},
    "سایر مشخصات": {
      "حس‌گرها": "اثرانگشت زیر صفحه نمایش اپتیکال (FingerPrint|Under-Display - Optical), قطب‌نما (Compass), شتاب‌سنج (Accelerometer), ژیروسکوپ (Gyro)",
      "ظرفیت باتری": "5000 میلی آمپر ساعت",
      "توان شارژ": "45 وات",
      "قابلیت‌های شارژ": "شارژ باسیم"
    }
  }
}
```

### snappshop

#### `ss_search`

Request:

```json
{
  "query": "headphones",
  "page": 1
}
```

Response:

```json
{
  "total": 123,
  "page": 1,
  "pages": 11,
  "items": [
    {
      "id": "ID_032",
      "product_id": "ID_033",
      "title": "هدفون داخل گوشی شیائومی مدل Headphone Pro Hd Hi-Res",
      "colors": [
        "نقره‌ای-طوسی"
      ],
      "url": "https://snappshop.ir/product/snp-1844312693"
    },
    {
      "id": "ID_034",
      "product_id": "ID_035",
      "title": "هدست گیمینگ میکروفن خلبانی گرین لاین مدل  Specter Gaming Headphone GL-HP53",
      "price": 8633000,
      "list_price": 8900000,
      "discount_percent": 3,
      "colors": [
        "مشکی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1490647124"
    },
    {
      "id": "ID_036",
      "product_id": "ID_037",
      "title": "هدست بلوتوثی انکر مدل SoundCore Life Q35",
      "colors": [
        "مشکی"
      ],
      "url": "https://snappshop.ir/product/snp-770876409"
    },
    {
      "id": "ID_038",
      "product_id": "ID_039",
      "title": "هدست تک گوش القایی بلوتوث کاکوسیگا مدل ksc-1115",
      "price": 2500000,
      "colors": [
        "مشکی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1450153939"
    },
    {
      "id": "ID_040",
      "product_id": "ID_041",
      "title": "هدفون بی سیم مدل wireless مدل 1400_p47",
      "colors": [
        "آبی",
        "قرمز"
      ],
      "url": "https://snappshop.ir/product/snp-2027698848"
    },
    {
      "id": "ID_042",
      "product_id": "ID_043",
      "title": "هدست بلوتوثی ایکس انرژی مدل X-1020",
      "price": 3889000,
      "list_price": 4455000,
      "discount_percent": 13,
      "colors": [
        "مشکی",
        "نقره‌ای-طوسی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1646047874"
    },
    {
      "id": "ID_044",
      "product_id": "ID_045",
      "title": "هدفون بلوتوثی مدل Pro 5S 2021",
      "price": 809000,
      "colors": [
        "سفید"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1229366928"
    },
    {
      "id": "ID_046",
      "product_id": "ID_047",
      "title": "هدفون مدل L29 BASS EARPHOne",
      "price": 350000,
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-2047727334"
    },
    {
      "id": "ID_048",
      "product_id": "ID_049",
      "title": "هدفون مک دودو (Mcdodo) مدل اچ پی-7500",
      "price": 2634950,
      "list_price": 3000000,
      "discount_percent": 13,
      "colors": [
        "سفید"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1794525022"
    },
    {
      "id": "ID_050",
      "product_id": "ID_051",
      "title": "هدفون بلوتوثی ایس فست مدل H13",
      "price": 4999000,
      "list_price": 5999000,
      "discount_percent": 17,
      "colors": [
        "مشکی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-443247395"
    },
    {
      "id": "ID_052",
      "product_id": "ID_053",
      "title": "هدفون بی سیم تی سی اچ مدل Black Blade L10",
      "price": 3310000,
      "colors": [
        "مشکی",
        "آبی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1570290874"
    },
    {
      "id": "ID_054",
      "product_id": "ID_055",
      "title": "هدفون با سیم اوی مدل PC-10T",
      "colors": [
        "مشکی"
      ],
      "url": "https://snappshop.ir/product/snp-13703410"
    }
  ]
}
```

#### `ss_product`

Request:

```json
{
  "product": "1844312693"
}
```

Response:

```json
{
  "id": "ID_032",
  "title": "هدفون داخل گوشی شیائومی مدل Headphone Pro Hd Hi-Res",
  "title_en": null,
  "brand": "شیائومی",
  "categories": [
    "دیجیتال",
    "گجت های پوشیدنی",
    "هدفون، هدست و هندزفری"
  ],
  "category_id": "x0QZq8",
  "rating": 0,
  "rating_count": 0,
  "review_count": 0,
  "price_from": 520000,
  "offer_count": 1,
  "seller_count": 1,
  "offers": [
    {
      "seller": "آسان دیجیتال",
      "seller_id": "ID_056",
      "price": 520000,
      "stock": 1,
      "seller_rating": "excellent",
      "warranty": "گارانتی سلامت فیزیکی کالا",
      "delivery": [
        "express"
      ],
      "variant": "رنگ: نقره ای"
    }
  ],
  "specs": {
    "وزن": "17 گرم",
    "نحوه اتصال": "باسیم",
    "نوع گوشی": "دو گوشی",
    "اقلام همراه": "4 عدد سرگوشی سیلیکونی در سایزهای متفاوت"
  },
  "description": null,
  "images": [
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db5a6e01.jpg",
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db59ecff.jpg",
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db597c4d.jpg",
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db58ffa7.jpg",
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db588153.jpg",
    "https://cdn.snappshop.ir/70/81/2/product_image/zoodfood/63bd6db57e4fe.jpg"
  ],
  "installment": "4 قسط ماهیانه (بدون کارمزد)",
  "warning": null
}
```

## Interpretation limits

- A schema proves parameter and tool shape, not that a provider returns phone data for every category or business.
- The observed `phones` fields on Neshan/Balad and `phone` on an Emalls shop profile are provider response fields; the values were masked. This does not prove every returned number is a mobile or eligible public business contact.
- Basalam, Digikala, SnappShop, Torob, Rasmio, Iran Jobs, and Quera did not produce a confirmed public business mobile in these limited samples. That is not proof those sources never expose one.
- Marketplace seller information is associated only when the seller ID matches the offer/profile node. An unrelated seller's contact is never attached to another seller.
- For account-like nested data, the application excludes phone candidates from extraction and redacts values in retained raw evidence. Explicit public contact branches remain eligible.
- Provider data, schemas, quotas, and response fields can change. Repeat bounded live probes before relying on these observations in production.
