# Theme System - Response Styling Variations

## Overview

The agentic search service supports **5 beautiful themes** with **6 different selection strategies** to introduce styling variations in responses.

---

## Available Themes

### 1. **Professional** (Default)
- **Colors**: Blue accent, dark gray text
- **Style**: Clean, corporate, data-focused
- **Best for**: Business, analytics, formal queries
- **Example**: Financial reports, market analysis

### 2. **Minimal**
- **Colors**: Monochrome (black/gray)
- **Style**: Ultra-clean, distraction-free
- **Best for**: Simple informational queries
- **Example**: Definitions, basic facts

### 3. **Dark**
- **Colors**: Dark background, cyan accents
- **Style**: Developer-friendly, easy on eyes
- **Best for**: Technical queries, night viewing
- **Example**: Code searches, API documentation

### 4. **Vibrant**
- **Colors**: Orange accent, warm backgrounds
- **Style**: Energetic, modern, eye-catching
- **Best for**: News, events, trending topics
- **Example**: Latest updates, breaking news

### 5. **Nature**
- **Colors**: Green/teal accents, earth tones
- **Style**: Organic, calming
- **Best for**: Environmental, climate queries
- **Example**: Climate events, sustainability topics

---

## Theme Selection Strategies

### Strategy 1: **Auto** (Recommended Default)
Intelligently selects theme based on query content:

```python
# Uses keyword detection
"climate change events" → nature
"stock market analysis" → professional
"latest tech news" → vibrant
"API documentation" → dark
```

**How it works:**
1. Tries intent classification if available
2. Falls back to keyword detection
3. Uses weighted random as final fallback

### Strategy 2: **Intent**
Based on query intent classification:

```python
ANALYTICAL/COMPARATIVE → professional
INFORMATIONAL → minimal
TEMPORAL/TRENDING → vibrant
SPECIFIC/TECHNICAL → dark
MULTI-ENTITY → nature
```

### Strategy 3: **Time**
Based on time of day:

```python
Morning (6-12) → vibrant (energetic)
Afternoon (12-18) → professional (work hours)
Evening (18-22) → nature (calming)
Night (22-6) → dark (easy on eyes)
```

### Strategy 4: **Keywords**
Detects keywords in query:

```python
# Financial
"stock", "market", "revenue" → professional

# Environment
"climate", "green", "sustainability" → nature

# Technology
"code", "api", "developer" → dark

# News
"news", "latest", "event" → vibrant

# Default
Other queries → minimal
```

### Strategy 5: **Weighted Random**
Random with probabilities:

```python
professional: 35% (most versatile)
minimal: 25% (clean)
vibrant: 20% (energetic)
nature: 15% (unique)
dark: 5% (specialty)
```

### Strategy 6: **Random**
Pure random selection (all themes equal probability)

---

## API Usage

### Basic Request (Auto Selection)

```bash
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "latest climate events in Europe",
    "enabled_tools": ["search_events"]
  }'
```

**Result**: Auto-detects "climate" keyword → **nature theme**

### Force Specific Theme

```bash
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "stock market trends",
    "enabled_tools": ["search_stories"],
    "theme": "dark",
    "theme_strategy": "auto"
  }'
```

**Result**: User preference overrides auto → **dark theme**

### Time-Based Selection

```bash
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "Tesla news",
    "theme_strategy": "time"
  }'
```

**Result**:
- 10 AM → **vibrant** (morning energy)
- 3 PM → **professional** (work hours)
- 8 PM → **nature** (evening calm)
- 11 PM → **dark** (night mode)

### Intent-Based Selection

```bash
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "compare Tesla and Ford sales",
    "theme_strategy": "intent"
  }'
```

**Result**: COMPARATIVE intent → **professional theme**

### Weighted Random

```bash
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "search anything",
    "theme_strategy": "weighted"
  }'
```

**Result**: Random with 35% chance professional, 25% minimal, etc.

---

## Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | ✅ Yes | - | User search query |
| `enabled_tools` | array | ❌ No | [] | List of enabled MCP tools |
| `session_id` | string | ❌ No | auto | Conversation session ID |
| `theme` | string | ❌ No | null | Force specific theme (overrides strategy) |
| `theme_strategy` | string | ❌ No | "auto" | Selection strategy (see below) |

### Valid `theme` Values
- `"professional"` - Blue accent, corporate
- `"minimal"` - Monochrome, clean
- `"dark"` - Dark mode, cyan accents
- `"vibrant"` - Orange, energetic
- `"nature"` - Green, organic

### Valid `theme_strategy` Values
- `"auto"` - Smart selection (intent → keywords → weighted)
- `"intent"` - Based on query intent
- `"time"` - Based on time of day
- `"keywords"` - Based on query keywords
- `"weighted"` - Weighted random
- `"random"` - Pure random

---

## Priority Order

Theme selection follows this priority:

1. **User Preference** (`theme` parameter) - Highest priority
2. **Strategy** (`theme_strategy` parameter)
3. **Weighted Random** - Fallback if strategy fails

```python
# Example priority chain
if user_theme:
    return user_theme  # User explicitly wants "dark"
elif strategy == "intent" and has_intent:
    return theme_from_intent  # ANALYTICAL → professional
elif strategy == "keywords":
    return theme_from_keywords  # "climate" → nature
else:
    return weighted_random  # 35% professional, 25% minimal, etc.
```

---

## Examples by Use Case

### Use Case 1: User Preference (Admin Panel)
Allow users to save their favorite theme:

```javascript
// Frontend: User settings
const userTheme = localStorage.getItem('preferred_theme') || 'professional';

fetch('/search', {
  method: 'POST',
  body: JSON.stringify({
    query: searchQuery,
    theme: userTheme  // Always use user's preference
  })
});
```

### Use Case 2: Context-Aware (Smart App)
Detect context and auto-select:

```javascript
// App detects night mode
const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
const strategy = isDarkMode ? 'time' : 'auto';

fetch('/search', {
  method: 'POST',
  body: JSON.stringify({
    query: searchQuery,
    theme_strategy: strategy
  })
});
```

### Use Case 3: Category Pages
Different themes for different sections:

```javascript
const sectionThemes = {
  '/business': 'professional',
  '/tech': 'dark',
  '/environment': 'nature',
  '/news': 'vibrant'
};

const theme = sectionThemes[currentSection] || null;

fetch('/search', {
  method: 'POST',
  body: JSON.stringify({
    query: searchQuery,
    theme: theme  // Section-specific theme
  })
});
```

---

## Implementation Details

### Files Modified

1. **theme_selector.py** (NEW)
   - Smart theme selection logic
   - 6 selection strategies
   - ~250 lines of selection algorithms

2. **state_definition.py**
   - Added `theme_preference`, `theme_strategy`, `response_theme` fields
   - Lines 84-87

3. **nodes.py**
   - Integrated smart theme selection
   - Lines 126-137 in `parallel_initialization_node`

4. **server.py**
   - Added `theme` and `theme_strategy` to SearchRequest
   - Lines 175-176, 179-186, 347-354

---

## Theme Color Reference

```python
THEMES = {
    "professional": {
        "primary_color": "#3498db",      # Blue
        "text_color": "#2c3e50",         # Dark gray
        "bg_light": "#f8f9fa",           # Light gray
    },
    "minimal": {
        "primary_color": "#000000",      # Black
        "text_color": "#333333",         # Dark gray
        "bg_light": "#f5f5f5",           # Very light gray
    },
    "dark": {
        "primary_color": "#00d4ff",      # Cyan
        "text_color": "#e4e4e4",         # Light gray
        "bg_light": "#2a2a2a",           # Dark gray
    },
    "vibrant": {
        "primary_color": "#ff6b35",      # Orange
        "text_color": "#2d3436",         # Dark gray
        "bg_light": "#fff5e6",           # Warm light
    },
    "nature": {
        "primary_color": "#27ae60",      # Green
        "text_color": "#2c3e50",         # Dark blue-gray
        "bg_light": "#f0fdf4",           # Very light green
    },
}
```

---

## Testing

```bash
# Test smart theme selection
python ollama_query_agent/theme_selector.py

# Test different strategies
curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "climate news", "theme_strategy": "auto"}'

curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "any query", "theme_strategy": "time"}'

curl -X POST http://localhost:8023/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "test", "theme": "vibrant"}'
```

---

## Benefits

✅ **Variety**: 5 distinct themes prevent response fatigue
✅ **Smart**: Auto-selection matches content to theme
✅ **Flexible**: 6 strategies for different use cases
✅ **User Control**: Override with explicit preference
✅ **Context-Aware**: Time-based and keyword detection
✅ **Zero Latency**: Theme selection is instant (0ms overhead)

---

## Future Enhancements

Potential additions:
- Custom theme creation API
- User-uploadable color schemes
- A/B testing different themes
- Analytics on theme preferences
- Seasonal themes (holiday colors)
- Brand-specific themes (corporate colors)
