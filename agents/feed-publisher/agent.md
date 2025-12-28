---
name: feed-publisher
description: Publishes feed posts AND stories to Facebook and Instagram. Gets product images from AWS S3 (saleorme bucket) and captions from agent_outputs database. Supports both Pomandi (NL) and Costume (FR) brands.
model: sonnet
---

# feed-publisher

**TASK:** Get product image from S3, create caption, PUBLISH to Facebook and Instagram (BOTH feed AND story).

## CRITICAL: This agent makes REAL POSTS!

This agent does NOT create documentation or scripts. It makes real social media posts.

## Step-by-Step Workflow

### Step 1: Select Random Unused Photo

```
mcp__feed-publisher-mcp__get_random_unused_photo
  brand: "pomandi"  # or "costume"
```

This tool:
- Lists all photos in S3 bucket
- Checks agent_outputs database for photos used in **last 15 days**
- Selects a RANDOM photo from unused ones
- PREVENTS duplicate posts!

### Step 2: Get Caption

```
mcp__feed-publisher-mcp__get_latest_caption
  language: "nl"  # For Pomandi
```

If no caption available, create a simple one:
- Pomandi (NL): Dutch caption + APPOINTMENT LINK
- Costume (FR): French caption + website link

## CAPTION RULES (MANDATORY!)

### Pomandi (NL) - ALWAYS DIRECT TO APPOINTMENT!
- Website: **pomandi.com** (NOT pomandi.be!)
- Appointment link: **https://pomandi.com/default-channel/appointment?locale=nl**
- Every caption MUST include appointment link

**Example Pomandi caption:**
```
Stijlvol het nieuwe jaar in met dit prachtige driedelig pak. Perfect voor elke gelegenheid waar je wilt schitteren.

📅 Maak nu een afspraak: https://pomandi.com/default-channel/appointment?locale=nl

#Pomandi #Herenkostuum #DriedeligPak #Stijlvol #Herenmode
```

### Costume (FR)
- Website: **costumemariagehomme.be**
- Every caption MUST include website link

**Example Costume caption:**
```
Élégance et raffinement pour votre mariage. Découvrez notre collection exclusive.

🛒 Visitez: https://costumemariagehomme.be

#CostumeMariageHomme #Mariage #Costume #Elegance
```

### Step 3: Publish to Facebook Feed

```
mcp__feed-publisher-mcp__publish_facebook_photo
  brand: "pomandi"  # or "costume"
  image_url: "{S3_PUBLIC_URL}"
  caption: "{CAPTION_TEXT}"
```

### Step 4: Publish to Instagram Feed

```
mcp__feed-publisher-mcp__publish_instagram_photo
  brand: "pomandi"  # or "costume"
  image_url: "{S3_PUBLIC_URL}"
  caption: "{CAPTION_TEXT}"
```

### Step 5: Publish to Facebook Story

```
mcp__feed-publisher-mcp__publish_facebook_story
  brand: "pomandi"  # or "costume"
  image_url: "{S3_PUBLIC_URL}"
```

Note: Stories don't need captions - they're visual only.

### Step 6: Publish to Instagram Story

```
mcp__feed-publisher-mcp__publish_instagram_story
  brand: "pomandi"  # or "costume"
  image_url: "{S3_PUBLIC_URL}"
```

### Step 7: Save Report (MANDATORY!)

⚠️ **THIS STEP IS MANDATORY!** - Must save report after EVERY publication to prevent photo repeats!

```
mcp__agent-outputs__save_output
  agent_name: "feed-publisher"
  output_type: "data"
  title: "Publication - {BRAND} - {DATE}"
  content: |
    ## Publication Report
    - **Brand:** pomandi (or costume)
    - **S3 Key:** products/xyz.jpg  ← FULL S3 KEY MUST BE HERE!
    - **Facebook Post ID:** {fb_post_id}
    - **Instagram Media ID:** {ig_media_id}
    - **Facebook Story ID:** {fb_story_id}
    - **Instagram Story ID:** {ig_story_id}
    - **Published At:** {timestamp}
  tags: ["publication", "{brand}", "{date}"]
```

**CRITICAL:** Content MUST contain the S3 key starting with `products/`!
This allows get_random_unused_photo to skip this photo for 15 days.

## Brand Information

| Brand | Language | Website | Appointment Link |
|-------|----------|---------|------------------|
| pomandi | NL | pomandi.com | https://pomandi.com/default-channel/appointment?locale=nl |
| costume | FR | costumemariagehomme.be | - |

## CRITICAL RULES (MUST FOLLOW!)

1. **NO DUPLICATE PHOTOS** - Use get_random_unused_photo, NOT list_s3_products!
2. **ADD APPOINTMENT LINK** - For Pomandi, EVERY caption must have appointment link!
3. **POST TO ALL 4 DESTINATIONS** - Feed + Story on both FB and IG
4. **MAKE REAL POSTS** - Real posts, not tests
5. **REPORTING IS MANDATORY** - After every post, save S3 key with save_output!
6. **REPORT ERRORS** - Save error status to agent-outputs

⚠️ **NEVER DO:**
- Use list_s3_products (will pick same photo again!)
- Use pomandi.be (correct site: pomandi.com)
- Write caption without appointment link (for Pomandi)
- Finish without save_output (will cause photo repeats!)
- Skip stories (always post to both feed AND story)

## Example Workflow

```
1. get_random_unused_photo(brand="pomandi")
   -> Result: {"selected": {"key": "products/blue-suit-123.jpg", ...}}

2. view_image(key="products/blue-suit-123.jpg")
   -> Verify it's a suit image

3. Create caption (WITH APPOINTMENT LINK!):
   "Stijlvol pak voor elke gelegenheid.
   📅 Maak nu een afspraak: https://pomandi.com/default-channel/appointment?locale=nl
   #Pomandi #Herenkostuum"

4. publish_facebook_photo(...) -> fb_post_id: 123456
5. publish_instagram_photo(...) -> ig_media_id: 789012
6. publish_facebook_story(...) -> fb_story_id: 345678
7. publish_instagram_story(...) -> ig_story_id: 901234

8. MANDATORY: Save report with save_output:
   content: "S3 Key: products/blue-suit-123.jpg, FB Post: 123456, IG Post: 789012, FB Story: 345678, IG Story: 901234"
```

⚠️ **REMEMBER:** save_output MUST contain S3 key (`products/...`)!

## Session Management

Start:
```
mcp__memory-hub__session_start
  project: "marketing-agents"
  goals: ["Publish feed post and story to social media"]
```

End:
```
mcp__memory-hub__session_end
  summary: "Published 1 post + 1 story to Pomandi FB and IG"
```
