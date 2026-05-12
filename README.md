# 🤖 AI Viral News

Curated viral AI news from Reddit & tech blogs — updated every 4 hours.

**📡 RSS Feed:** https://arief-drip.github.io/ai-viral-news/feed.xml  
**📊 JSON:** https://arief-drip.github.io/ai-viral-news/feed.json  
**🌐 Landing:** https://arief-drip.github.io/ai-viral-news/

## Sources

| Platform | Details |
|----------|---------|
| **Reddit** | r/artificial, r/MachineLearning, r/LocalLLaMA, r/singularity, r/OpenAI, r/StableDiffusion, r/technology |
| **Blogs** | TechCrunch AI, The Verge AI, Ars Technica, VentureBeat AI, MIT Tech Review, HuggingFace Blog |

## How it works

1. **Reddit** — polled via public JSON endpoint (no API key needed)
2. **RSS sources** — fetched from top AI/tech blogs
3. **Filtered** by AI keywords + engagement threshold (100+ upvotes on Reddit)
4. **Generated** into RSS feed XML + JSON
5. **Published** to GitHub Pages (updated every 4 hours via GitHub Actions + local cron)

## Local Setup

```bash
git clone https://github.com/arief-drip/ai-viral-news.git
cd ai-viral-news
python3 -m venv venv
source venv/bin/activate
pip install feedgen requests pyyaml
python scripts/update_feed.py
```

## Config

Edit `config.yaml` to customize:
- Subreddits & RSS sources
- Keywords & engagement thresholds
- Output settings
