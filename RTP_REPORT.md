# ChipCity — Monte Carlo RTP report

Generated 2026-11-14 12:09 UTC · 100,000 rounds per instant game, 20,000 per slot/card configuration · 59.4s

| Game | Configuration | Rounds | Measured RTP | Theoretical | Diff | Std. error |
|---|---|---:|---:|---:|---:|---:|
| dice | under 50 | 100,000 | 99.06% | 99.00% | +0.06% | 0.31% |
| dice | over 95 | 100,000 | 97.17% | 99.00% | -1.83% | 1.35% |
| limbo | 2x | 100,000 | 98.85% | 99.00% | -0.15% | 0.32% |
| limbo | 10x | 100,000 | 99.37% | 99.00% | +0.37% | 0.95% |
| coinflip | cash out 1 | 100,000 | 98.83% | 99.00% | -0.17% | 0.31% |
| plinko | 12 rows medium | 100,000 | 99.23% | 99.14% | +0.09% | 0.40% |
| plinko | 16 rows high | 100,000 | 99.61% | 98.85% | +0.76% | 1.74% |
| keno | 5 picks classic | 100,000 | 98.34% | 99.00% | -0.67% | 5.49% |
| diamonds | draw 5 | 100,000 | 94.88% | 99.00% | -4.12% | 2.81% |
| cases | vault | 100,000 | 98.66% | 98.86% | -0.20% | 0.48% |
| bars | bar 1 medium | 100,000 | 99.03% | 98.99% | +0.03% | 0.43% |
| tarot | 3 cards | 100,000 | 98.03% | 98.94% | -0.91% | 0.53% |
| darts | medium | 100,000 | 98.84% | 99.00% | -0.16% | 0.25% |
| sicbo | small | 100,000 | 96.67% | 97.22% | -0.55% | 0.32% |
| rps | continue draws | 100,000 | 98.63% | 99.00% | -0.37% | 0.31% |
| slide | target 2.16x | 100,000 | 99.55% | 99.12% | +0.42% | 0.34% |
| mines | 3 mines, 3 picks | 100,000 | 98.99% | 99.00% | -0.01% | 0.22% |
| dragontower | medium | 100,000 | 99.39% | 99.00% | +0.39% | 0.48% |
| pump | medium 3 pumps | 100,000 | 99.00% | 99.00% | +0.00% | 0.28% |
| chicken | medium 3 lanes | 100,000 | 98.98% | 99.00% | -0.02% | 0.21% |
| moles | medium | 100,000 | 99.05% | 99.00% | +0.05% | 0.37% |
| snakes | medium 3 rolls | 100,000 | 98.84% | 99.00% | -0.16% | 0.27% |
| wheel | 20 seg medium | 100,000 | 99.31% | 98.90% | +0.41% | 0.25% |
| roulette | red | 100,000 | 97.26% | 97.30% | -0.04% | 0.32% |
| baccarat | banker | 100,000 | 99.03% | 98.94% | +0.09% | 0.29% |
| crash | auto 2x | 100,000 | 99.21% | 99.00% | +0.21% | 0.32% |
| hilo | 3 guesses | 100,000 | 100.27% | 99.00% | +1.27% | 1.97% |
| pharaoh | spin | 20,000 | 98.57% | 99.11% | -0.54% | 1.80% |
| ronin | spin | 20,000 | 98.56% | 99.02% | -0.47% | 1.82% |
| spellbook | spin | 20,000 | 98.49% | 98.97% | -0.49% | 1.81% |
| blackjack | basic strategy | 20,000 | 97.21% | 99.54% | -2.33% | 0.69% |
| videopoker | simple strategy | 20,000 | 96.92% | 99.54% | -2.62% | 1.32% |

Theoretical values are the game's published tables. Blackjack (0.9954) and Video Poker (0.9954)
assume strong play; the simulated strategies are conservative simplifications, so their measured
values are slightly lower and are reported rather than asserted. Roulette (97.30%), Sic Bo (97.22%)
and Baccarat (98.94%) use their standard casino pay tables, as documented in DECISIONS.md.

Run the full spec sample with:

```bash
python -m scripts.rtp_report --rounds 1000000 --slow-rounds 200000
```
