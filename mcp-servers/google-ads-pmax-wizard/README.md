# Google Ads Performance Max Wizard MCP Server

Step-by-step Performance Max kampanya oluşturma sihirbazı. Her adımı kontrollü şekilde yürütmenizi sağlar.

## Genel Bakış

Bu MCP server, Google Ads Performance Max kampanyalarını adım adım oluşturmanızı sağlar. Tek seferde her şeyi oluşturmak yerine, her adımı ayrı ayrı kontrol edebilir ve doğrulayabilirsiniz.

## Kurulum

### Gereksinimler
- Python 3.9+
- google-ads Python kütüphanesi
- mcp Python kütüphanesi

### .mcp.json Konfigürasyonu

```json
{
  "google-ads-pmax-wizard": {
    "command": "/workspace/server-data/mcp-servers/.venv/bin/python",
    "args": ["/workspace/server-data/mcp-servers/google-ads-pmax-wizard/server.py"],
    "env": {
      "GOOGLE_ADS_YAML_PATH": "/workspace/server-data/google-ads.yaml",
      "GOOGLE_ADS_CUSTOMER_ID": "${GOOGLE_ADS_CUSTOMER_ID}"
    }
  }
}
```

### google-ads.yaml Formatı

```yaml
developer_token: "YOUR_DEVELOPER_TOKEN"
client_id: "YOUR_CLIENT_ID.apps.googleusercontent.com"
client_secret: "YOUR_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
login_customer_id: "1234567890"
```

---

## Kampanya Oluşturma Adımları

Performance Max kampanyası oluşturmak için aşağıdaki adımları sırayla takip edin:

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Budget      →  STEP 2: Campaign  →  STEP 3: Targeting │
│  (Bütçe oluştur)        (Kampanya oluştur)   (Hedefleme ekle)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Asset Group  →  STEP 5: Assets    →  STEP 6: Activate │
│  (Asset grubu oluştur)   (İçerik ekle)        (Kampanyayı aç)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tool Referansı

### STEP 1: Bütçe Oluşturma

#### `pmax_step1_create_budget`

Kampanya için günlük bütçe oluşturur.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `name` | string | Evet | Bütçe adı (örn: "Pomandi-PMax-Budget") |
| `amount_micros` | integer | Evet | Günlük bütçe (mikro birim: €50 = 50000000) |

**Örnek:**
```json
{
  "name": "Pomandi-Trouwpak-Budget",
  "amount_micros": 50000000
}
```

**Dönüş:**
```json
{
  "success": true,
  "budget_id": "123456789",
  "budget_resource_name": "customers/1234567890/campaignBudgets/123456789",
  "daily_budget_euros": 50.0,
  "next_step": "pmax_step2_create_campaign"
}
```

**Not:**
- €1 = 1,000,000 mikro birim
- €50/gün = 50000000 mikro

---

### STEP 2: Kampanya Oluşturma

#### `pmax_step2_create_campaign`

Performance Max kampanyası oluşturur.

**Parametreler:**
| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `budget_id` | string | Evet | - | Step 1'den dönen budget_id |
| `name` | string | Evet | - | Kampanya adı |
| `bidding_strategy` | string | Hayır | "MAXIMIZE_CONVERSIONS" | Teklif stratejisi |
| `target_roas` | float | Hayır | - | Hedef ROAS (sadece MAXIMIZE_CONVERSION_VALUE için) |

**Teklif Stratejileri:**
- `MAXIMIZE_CONVERSIONS` - Dönüşüm sayısını maksimize et
- `MAXIMIZE_CONVERSION_VALUE` - Dönüşüm değerini maksimize et (target_roas gerekir)

**Örnek:**
```json
{
  "budget_id": "123456789",
  "name": "Pomandi Trouwpak PMax",
  "bidding_strategy": "MAXIMIZE_CONVERSIONS"
}
```

**Dönüş:**
```json
{
  "success": true,
  "campaign_id": "987654321",
  "campaign_resource_name": "customers/1234567890/campaigns/987654321",
  "status": "PAUSED",
  "next_step": "pmax_step3_set_targeting"
}
```

---

### STEP 3: Hedefleme Ayarlama

#### `pmax_step3_set_targeting`

Ülke ve dil hedeflemesi ekler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `campaign_id` | string | Evet | - | Step 2'den dönen campaign_id |
| `countries` | array | Hayır | ["BE"] | Ülke kodları |
| `languages` | array | Hayır | ["nl"] | Dil kodları |
| `regions` | array | Hayır | - | Bölge/il kodları |
| `cities` | array | Hayır | - | Şehir kodları |

**Desteklenen Ülkeler:**
| Kod | Ülke | Criterion ID |
|-----|------|--------------|
| BE | Belçika | 2056 |
| NL | Hollanda | 2528 |
| DE | Almanya | 2276 |
| FR | Fransa | 2250 |
| LU | Lüksemburg | 2442 |

**Desteklenen Diller:**
| Kod | Dil | Criterion ID |
|-----|-----|--------------|
| nl | Hollandaca | 1010 |
| fr | Fransızca | 1002 |
| de | Almanca | 1001 |
| en | İngilizce | 1000 |

**Örnek - Sadece Ülke:**
```json
{
  "campaign_id": "987654321",
  "countries": ["BE", "NL"],
  "languages": ["nl"]
}
```

**Örnek - Belirli Bölgeler:**
```json
{
  "campaign_id": "987654321",
  "regions": ["antwerp", "limburg_be"],
  "languages": ["nl"]
}
```

**Örnek - Belirli Şehirler:**
```json
{
  "campaign_id": "987654321",
  "cities": ["brasschaat", "genk", "antwerpen"],
  "languages": ["nl"]
}
```

**Dönüş:**
```json
{
  "success": true,
  "campaign_id": "987654321",
  "geo_targets_added": 2,
  "language_targets_added": 1,
  "next_step": "pmax_step4_create_asset_group"
}
```

---

### STEP 4: Asset Group Oluşturma

#### `pmax_step4_create_asset_group`

Kampanya için asset grubu oluşturur.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `campaign_id` | string | Evet | Step 2'den dönen campaign_id |
| `name` | string | Evet | Asset grubu adı |
| `final_url` | string | Evet | Hedef URL |

**Örnek:**
```json
{
  "campaign_id": "987654321",
  "name": "Trouwpakken Collectie",
  "final_url": "https://pomandi.com/collections/trouwpakken"
}
```

**Dönüş:**
```json
{
  "success": true,
  "asset_group_id": "456789123",
  "asset_group_resource_name": "customers/1234567890/assetGroups/456789123",
  "next_step": "pmax_step5a_add_headlines"
}
```

---

### STEP 5a: Başlıklar Ekleme

#### `pmax_step5a_add_headlines`

Reklam başlıkları ekler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `asset_group_id` | string | Evet | Step 4'ten dönen asset_group_id |
| `headlines` | array | Evet | Başlık listesi (min 3, max 15) |

**Kurallar:**
- Minimum 3 başlık gerekli
- Maximum 15 başlık eklenebilir
- Her başlık max 30 karakter

**Örnek:**
```json
{
  "asset_group_id": "456789123",
  "headlines": [
    "Premium Trouwpakken €320",
    "Maatpak in 15 Dagen",
    "1000+ Kostuums Op Voorraad",
    "Gratis Styling Advies",
    "Op Maat Gemaakt"
  ]
}
```

**Dönüş:**
```json
{
  "success": true,
  "asset_group_id": "456789123",
  "headlines_added": 5,
  "next_step": "pmax_step5b_add_descriptions"
}
```

---

### STEP 5b: Açıklamalar Ekleme

#### `pmax_step5b_add_descriptions`

Reklam açıklamaları ekler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `asset_group_id` | string | Evet | Step 4'ten dönen asset_group_id |
| `descriptions` | array | Evet | Açıklama listesi (min 2, max 5) |

**Kurallar:**
- Minimum 2 açıklama gerekli
- Maximum 5 açıklama eklenebilir
- Her açıklama max 90 karakter

**Örnek:**
```json
{
  "asset_group_id": "456789123",
  "descriptions": [
    "Ontdek onze exclusieve trouwpakken collectie. Vanaf €320 met gratis styling.",
    "Premium maatpakken in Brasschaat & Genk. Van meting tot levering in 15 dagen."
  ]
}
```

**Dönüş:**
```json
{
  "success": true,
  "asset_group_id": "456789123",
  "descriptions_added": 2,
  "next_step": "pmax_step5c_add_images"
}
```

---

### STEP 5c: Görseller Ekleme

#### `pmax_step5c_add_images`

Reklam görselleri ekler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `asset_group_id` | string | Evet | Asset group ID |
| `marketing_images` | array | Evet | 1.91:1 marketing görselleri (URL listesi) |
| `square_images` | array | Evet | 1:1 kare görseller (URL listesi) |
| `logo_images` | array | Hayır | Logo görselleri (URL listesi) |
| `landscape_logo_images` | array | Hayır | Yatay logo görselleri (URL listesi) |

**Görsel Gereksinimleri:**
| Tip | En/Boy Oranı | Min Boyut | Önerilen |
|-----|--------------|-----------|----------|
| Marketing Image | 1.91:1 | 600x314 | 1200x628 |
| Square Image | 1:1 | 300x300 | 1200x1200 |
| Logo | 1:1 | 128x128 | 1200x1200 |
| Landscape Logo | 4:1 | 512x128 | 1200x300 |

**Örnek:**
```json
{
  "asset_group_id": "456789123",
  "marketing_images": [
    "https://cdn.pomandi.com/images/trouwpak-hero.jpg",
    "https://cdn.pomandi.com/images/showroom.jpg"
  ],
  "square_images": [
    "https://cdn.pomandi.com/images/suit-square.jpg"
  ],
  "logo_images": [
    "https://cdn.pomandi.com/images/logo.png"
  ]
}
```

**Dönüş:**
```json
{
  "success": true,
  "asset_group_id": "456789123",
  "images_added": {
    "marketing": 2,
    "square": 1,
    "logo": 1
  },
  "next_step": "pmax_step5d_add_audience_signals"
}
```

---

### STEP 5d: Hedef Kitle Sinyalleri (Opsiyonel)

#### `pmax_step5d_add_audience_signals`

Hedef kitle sinyalleri ekler. Google'ın optimizasyonuna yardımcı olur.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `asset_group_id` | string | Evet | Asset group ID |
| `custom_audiences` | array | Hayır | Özel kitle ID'leri |
| `interests` | array | Hayır | İlgi alanı kategorileri |
| `demographics` | object | Hayır | Demografik hedefleme |

**Örnek:**
```json
{
  "asset_group_id": "456789123",
  "interests": ["weddings", "mens_fashion", "formal_wear"],
  "demographics": {
    "age_range": ["25-34", "35-44"],
    "gender": ["male"]
  }
}
```

**Dönüş:**
```json
{
  "success": true,
  "asset_group_id": "456789123",
  "audience_signals_added": true,
  "next_step": "pmax_step6_activate_campaign"
}
```

---

### STEP 6: Kampanyayı Aktifleştirme

#### `pmax_step6_activate_campaign`

Kampanyayı aktif duruma getirir.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `campaign_id` | string | Evet | Kampanya ID |

**Örnek:**
```json
{
  "campaign_id": "987654321"
}
```

**Dönüş:**
```json
{
  "success": true,
  "campaign_id": "987654321",
  "status": "ENABLED",
  "message": "Kampanya başarıyla aktifleştirildi"
}
```

---

## Yardımcı Tool'lar

### `pmax_get_campaign_status`

Kampanya durumunu ve asset bilgilerini sorgular.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `campaign_id` | string | Evet | Kampanya ID |

**Dönüş:**
```json
{
  "campaign_id": "987654321",
  "name": "Pomandi Trouwpak PMax",
  "status": "ENABLED",
  "bidding_strategy": "MAXIMIZE_CONVERSIONS",
  "budget": {
    "daily_euros": 50.0
  },
  "asset_groups": [
    {
      "id": "456789123",
      "name": "Trouwpakken Collectie",
      "headlines_count": 5,
      "descriptions_count": 2,
      "images_count": 4
    }
  ],
  "targeting": {
    "countries": ["BE", "NL"],
    "languages": ["nl"]
  }
}
```

---

### `pmax_list_available_locations`

Mevcut lokasyonları listeler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `country` | string | Hayır | - | Ülke kodu (BE veya NL) |
| `type` | string | Hayır | "all" | Tip: countries, regions, cities, all |

**Örnek - Belçika Şehirleri:**
```json
{
  "country": "BE",
  "type": "cities"
}
```

**Dönüş:**
```json
{
  "country": "BE",
  "type": "cities",
  "locations": [
    {"code": "brasschaat", "name": "Brasschaat", "id": 1001034, "province": "antwerp"},
    {"code": "genk", "name": "Genk", "id": 1001162, "province": "limburg_be"},
    {"code": "antwerpen", "name": "Antwerpen", "id": 1001456, "province": "antwerp"}
  ]
}
```

---

### `pmax_validate_assets`

Asset'lerin geçerliliğini kontrol eder.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `asset_group_id` | string | Evet | Asset group ID |

**Dönüş:**
```json
{
  "asset_group_id": "456789123",
  "valid": true,
  "validation": {
    "headlines": {"count": 5, "min": 3, "max": 15, "valid": true},
    "descriptions": {"count": 2, "min": 2, "max": 5, "valid": true},
    "marketing_images": {"count": 2, "min": 1, "max": 20, "valid": true},
    "square_images": {"count": 1, "min": 1, "max": 20, "valid": true}
  },
  "ready_to_activate": true
}
```

---

### `pmax_pause_campaign`

Kampanyayı duraklatır.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `campaign_id` | string | Evet | Kampanya ID |

---

### `pmax_delete_campaign`

Kampanyayı siler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Açıklama |
|-----------|-----|---------|----------|
| `campaign_id` | string | Evet | Kampanya ID |

---

### `pmax_list_campaigns`

Tüm Performance Max kampanyalarını listeler.

**Parametreler:**
| Parametre | Tip | Zorunlu | Varsayılan | Açıklama |
|-----------|-----|---------|------------|----------|
| `status` | string | Hayır | "all" | Filtre: all, enabled, paused |

---

## Tam Kampanya Oluşturma Örneği

Pomandi için düğün takımı kampanyası oluşturma:

```
# 1. Bütçe oluştur (€50/gün)
pmax_step1_create_budget(
  name="Pomandi-Trouwpak-Budget",
  amount_micros=50000000
)
→ budget_id: "123456789"

# 2. Kampanya oluştur
pmax_step2_create_campaign(
  budget_id="123456789",
  name="Pomandi Trouwpak PMax",
  bidding_strategy="MAXIMIZE_CONVERSIONS"
)
→ campaign_id: "987654321"

# 3. Hedefleme ayarla (Belçika & Hollanda, Hollandaca)
pmax_step3_set_targeting(
  campaign_id="987654321",
  countries=["BE", "NL"],
  languages=["nl"]
)

# 4. Asset grubu oluştur
pmax_step4_create_asset_group(
  campaign_id="987654321",
  name="Trouwpakken Collectie",
  final_url="https://pomandi.com/collections/trouwpakken"
)
→ asset_group_id: "456789123"

# 5a. Başlıklar ekle
pmax_step5a_add_headlines(
  asset_group_id="456789123",
  headlines=[
    "Premium Trouwpakken €320",
    "Maatpak in 15 Dagen",
    "1000+ Kostuums Op Voorraad",
    "Gratis Styling Advies",
    "Op Maat Gemaakt"
  ]
)

# 5b. Açıklamalar ekle
pmax_step5b_add_descriptions(
  asset_group_id="456789123",
  descriptions=[
    "Ontdek onze exclusieve trouwpakken. Vanaf €320 met gratis styling advies.",
    "Premium maatpakken in Brasschaat & Genk. Van meting tot levering in 15 dagen."
  ]
)

# 5c. Görseller ekle
pmax_step5c_add_images(
  asset_group_id="456789123",
  marketing_images=["https://cdn.pomandi.com/hero.jpg"],
  square_images=["https://cdn.pomandi.com/square.jpg"],
  logo_images=["https://cdn.pomandi.com/logo.png"]
)

# 5d. Hedef kitle sinyalleri (opsiyonel)
pmax_step5d_add_audience_signals(
  asset_group_id="456789123",
  interests=["weddings", "mens_fashion"]
)

# 6. Kampanyayı aktifleştir
pmax_step6_activate_campaign(
  campaign_id="987654321"
)
```

---

## Lokasyon Referansı

### Belçika (BE) Bölgeleri

| Kod | İsim | Criterion ID |
|-----|------|--------------|
| antwerp | Antwerp | 20315 |
| brussels | Brussels | 20316 |
| east_flanders | East Flanders | 20318 |
| flemish_brabant | Flemish Brabant | 20319 |
| hainaut | Hainaut | 20320 |
| liege | Liège | 20321 |
| limburg_be | Limburg (BE) | 20322 |
| luxembourg_be | Luxembourg (BE) | 20323 |
| namur | Namur | 20324 |
| walloon_brabant | Walloon Brabant | 20317 |
| west_flanders | West Flanders | 20325 |

### Belçika (BE) Popüler Şehirler

| Kod | İsim | Criterion ID | Bölge |
|-----|------|--------------|-------|
| brasschaat | Brasschaat | 1001034 | Antwerp |
| genk | Genk | 1001162 | Limburg |
| antwerpen | Antwerpen | 1001456 | Antwerp |
| brussel | Brussel | 1001501 | Brussels |
| gent | Gent | 1001468 | East Flanders |
| brugge | Brugge | 1001457 | West Flanders |
| leuven | Leuven | 1001497 | Flemish Brabant |
| mechelen | Mechelen | 1001479 | Antwerp |
| hasselt | Hasselt | 1001474 | Limburg |

### Hollanda (NL) Bölgeleri

| Kod | İsim | Criterion ID |
|-----|------|--------------|
| drenthe | Drenthe | 20634 |
| flevoland | Flevoland | 20635 |
| friesland | Friesland | 20636 |
| gelderland | Gelderland | 20637 |
| groningen | Groningen | 20638 |
| limburg_nl | Limburg (NL) | 20639 |
| north_brabant | North Brabant | 20640 |
| north_holland | North Holland | 20641 |
| overijssel | Overijssel | 20642 |
| south_holland | South Holland | 20643 |
| utrecht | Utrecht | 20644 |
| zeeland | Zeeland | 20645 |

### Hollanda (NL) Popüler Şehirler

| Kod | İsim | Criterion ID | Bölge |
|-----|------|--------------|-------|
| amsterdam | Amsterdam | 1010543 | North Holland |
| rotterdam | Rotterdam | 1010545 | South Holland |
| den_haag | Den Haag | 1010544 | South Holland |
| utrecht | Utrecht | 1010548 | Utrecht |
| eindhoven | Eindhoven | 1010555 | North Brabant |
| tilburg | Tilburg | 1010556 | North Brabant |
| maastricht | Maastricht | 1010557 | Limburg |

---

## Hata Kodları

| Kod | Açıklama | Çözüm |
|-----|----------|-------|
| `BUDGET_NOT_FOUND` | Bütçe bulunamadı | Step 1'i tekrar çalıştırın |
| `CAMPAIGN_NOT_FOUND` | Kampanya bulunamadı | Campaign ID'yi kontrol edin |
| `ASSET_GROUP_NOT_FOUND` | Asset grubu bulunamadı | Step 4'ü tekrar çalıştırın |
| `INSUFFICIENT_HEADLINES` | Yeterli başlık yok | Minimum 3 başlık ekleyin |
| `INSUFFICIENT_DESCRIPTIONS` | Yeterli açıklama yok | Minimum 2 açıklama ekleyin |
| `INVALID_IMAGE_URL` | Geçersiz görsel URL | URL'nin erişilebilir olduğunu kontrol edin |
| `HEADLINE_TOO_LONG` | Başlık çok uzun | Max 30 karakter |
| `DESCRIPTION_TOO_LONG` | Açıklama çok uzun | Max 90 karakter |

---

## İpuçları

1. **Her adımdan sonra doğrulayın:** `pmax_get_campaign_status` ile durumu kontrol edin
2. **Önce PAUSED oluşturun:** Kampanya PAUSED olarak oluşturulur, asset'ler tamamlandıktan sonra aktifleştirin
3. **Görsel boyutlarına dikkat:** Yanlış boyutlar reddedilebilir
4. **Karakter limitlerini aşmayın:** Başlık 30, açıklama 90 karakter
5. **Lokasyon kodlarını kullanın:** Şehir/bölge hedeflemesi için `pmax_list_available_locations` kullanın

---

## Dosya Yapısı

```
google-ads-pmax-wizard/
├── __init__.py
├── server.py          # Ana MCP server
├── geo_targets.py     # BE/NL lokasyon veritabanı
└── README.md          # Bu dosya
```

---

## Versiyon

- **v1.0.0** - İlk sürüm (2024-12-20)
  - Step-by-step kampanya oluşturma
  - BE/NL lokasyon desteği
  - 15 MCP tool
