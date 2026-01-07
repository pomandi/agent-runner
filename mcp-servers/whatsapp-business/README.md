# WhatsApp Business MCP Server

WhatsApp Business Cloud API entegrasyonu için MCP (Model Context Protocol) server.

## Özellikler

| Tool | Açıklama |
|------|----------|
| `send_message` | Text mesaj gönder (24 saat içinde yanıt veren kullanıcılara) |
| `send_template_message` | Template mesajı gönder (24 saat dışı konuşmalar için) |
| `send_document` | PDF, DOC vb. döküman gönder |
| `send_image` | Resim gönder |
| `get_message_status` | Mesaj durumunu kontrol et |
| `get_templates` | Mevcut template'leri listele |
| `get_phone_number_info` | WhatsApp numara bilgilerini al |

## Kurulum

### 1. Meta Developer Hesabı Kurulumu

1. https://developers.facebook.com adresine git
2. Yeni uygulama oluştur (Business tipi)
3. WhatsApp ürününü ekle

### 2. WhatsApp Business API Aktivasyonu

1. Meta Developer Console → WhatsApp → API Setup
2. Test numarası al veya kendi numaranı ekle
3. **Phone Number ID**'yi not al

### 3. Access Token Oluşturma

Kalıcı (permanent) token için:

1. Meta Business Settings → System Users
2. Yeni System User oluştur
3. WhatsApp uygulamasına erişim ver
4. Token oluştur - `whatsapp_business_messaging` izni seç
5. **Access Token**'ı not al

### 4. Environment Variables

`.env` dosyasına ekle:

```env
# WhatsApp Business API
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_ACCESS_TOKEN=EAAxxxxxx...
WHATSAPP_BUSINESS_ACCOUNT_ID=123456789012345
```

| Değişken | Açıklama | Zorunlu |
|----------|----------|---------|
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp numaranızın ID'si | Evet |
| `WHATSAPP_ACCESS_TOKEN` | Permanent access token | Evet |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | Business Account ID (template listesi için) | Hayır |

## Kullanım Örnekleri

### Text Mesaj Gönderme

```python
# Agent kullanımı
mcp__whatsapp-business__send_message(
    to="+32471234567",
    message="Merhaba! Bu bir test mesajıdır."
)
```

**Not**: Text mesaj sadece son 24 saat içinde size mesaj atan kullanıcılara gönderilebilir.

### Template Mesaj Gönderme

```python
# 24 saat dışı konuşmalar için template kullan
mcp__whatsapp-business__send_template_message(
    to="+32471234567",
    template_name="analytics_hourly_report",
    language_code="tr",
    body_parameters=["Rapor içeriği buraya..."]
)
```

### Döküman Gönderme

```python
mcp__whatsapp-business__send_document(
    to="+32471234567",
    document_url="https://example.com/report.pdf",
    filename="rapor.pdf",
    caption="Haftalık analiz raporu"
)
```

## Message Templates

WhatsApp Business API'de 24 saat dışında mesaj göndermek için onaylı template gerekli.

### Template Oluşturma

1. Meta Business Suite → WhatsApp Manager → Message Templates
2. "Create Template" tıkla
3. Kategori seç: UTILITY (bildirimler için)
4. Dil seç: Turkish (tr)
5. Template içeriği yaz

### Örnek Template

```
Template Adı: analytics_hourly_report
Kategori: UTILITY
Dil: Turkish (tr)

Header: 📊 Analytics Raporu
Body: {{1}}
Footer: Pomandi Analytics
```

**Onay süresi**: Genellikle birkaç saat, maksimum 24 saat.

## WhatsApp Mesaj Limitleri

| Tier | Limit | Nasıl Ulaşılır |
|------|-------|----------------|
| Tier 0 | 250 mesaj/gün | Yeni hesaplar |
| Tier 1 | 1,000 mesaj/gün | 1,000+ mesaj gönderince |
| Tier 2 | 10,000 mesaj/gün | Quality rating iyi olunca |
| Tier 3 | 100,000 mesaj/gün | Yüksek hacim |
| Tier 4 | Sınırsız | Enterprise |

## Maliyet

| Tip | Fiyat (Belçika) |
|-----|-----------------|
| Utility (bildirim) | ~$0.0180/mesaj |
| Marketing | ~$0.0582/mesaj |
| İlk 1,000 konuşma/ay | **Ücretsiz** |

## Entegrasyon Örneği: hourly-analytics-reporter

Agent'ın rapor göndermesi için `agent.md`'ye eklenecek adım:

```markdown
## ADIM 6: WhatsApp Bildirim

1. Rapor özetini oluştur (max 1024 karakter)
2. WhatsApp ile gönder:

mcp__whatsapp-business__send_template_message
- to: "+32XXXXXXXXX"
- template_name: "analytics_hourly_report"
- body_parameters: ["{{rapor_ozeti}}"]

3. Gönderim sonucunu logla
```

## Hata Kodları

| Kod | Açıklama | Çözüm |
|-----|----------|-------|
| 131030 | Recipient not opted in | Kullanıcı size mesaj atmamış, template kullan |
| 131051 | Invalid template | Template adı veya parametreleri yanlış |
| 190 | Invalid token | Access token süresi dolmuş |
| 100 | Invalid parameter | Telefon numarası formatı yanlış |

## Test

```bash
# Server'ı test et
cd /workspace/server-data/mcp-servers
.venv/bin/python whatsapp-business/server.py

# Veya Claude Code ile test et
# "WhatsApp numara bilgilerini getir" de
```

## Kaynaklar

- [WhatsApp Cloud API Docs](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Message Templates](https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates)
- [Pricing](https://developers.facebook.com/docs/whatsapp/pricing)
