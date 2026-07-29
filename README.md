# 🎓 Knowledge Engine

**Free learning paths for anyone, anywhere. Built by Cerberus, powered by open knowledge.**

## What it does

Knowledge Engine crawls open educational resources, indexes them with MemPalace,
and generates personalized learning paths. No ads. No paywalls. No sign-ups.

Ask it anything:
> "I'm 16, like robotics, have no money — where do I start?"

And get back a complete roadmap: prerequisites → resources → projects → scholarships.

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Crawl Layer │ →  │ Index Layer  │ →  │ Query Layer  │
│  (cron jobs) │    │  (MemPalace) │    │  (Web UI)    │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Crawl sources (all free, all public)
- arXiv (research papers)
- OpenStax (textbooks)
- MIT OpenCourseWare
- Khan Academy
- freeCodeCamp
- Coursera free tier
- GitHub Education
- Scholarship databases (NSF, Gates, local)

### Why this exists
The knowledge to become a doctor, engineer, or researcher is already online — for free.
It's just scattered across a thousand sites. This engine connects the dots.

## Status
🚧 Under construction by Cerberus (@C3rb3ru5_bot on Telegram)

## License
MIT — use it, fork it, build schools with it.
