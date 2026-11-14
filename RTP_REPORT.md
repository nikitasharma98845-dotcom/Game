# ChipCity — Monte Carlo RTP report

Generated 2026-11-14 12:55 UTC · 1,000,000 rounds per instant game, 200,000 per slot/card configuration · 590.3s

| Game | Configuration | Rounds | Measured RTP | Theoretical | Diff | Std. error |
|---|---|---:|---:|---:|---:|---:|
| dice | under 50 | 1,000,000 | 99.10% | 99.00% | +0.10% | 0.10% |
| dice | over 95 | 1,000,000 | 98.29% | 99.00% | -0.71% | 0.43% |
| limbo | 2x | 1,000,000 | 98.98% | 99.00% | -0.02% | 0.10% |
| limbo | 10x | 1,000,000 | 98.93% | 99.00% | -0.07% | 0.30% |
| coinflip | cash out 1 | 1,000,000 | 98.97% | 99.00% | -0.03% | 0.10% |
| plinko | 12 rows medium | 1,000,000 | 99.24% | 99.14% | +0.10% | 0.12% |
| plinko | 16 rows high | 1,000,000 | 99.86% | 98.85% | +1.01% | 0.57% |
| keno | 5 picks classic | 1,000,000 | 99.36% | 99.00% | +0.36% | 1.74% |
| diamonds | draw 5 | 1,000,000 | 99.21% | 99.00% | +0.21% | 1.00% |
| cases | vault | 1,000,000 | 98.95% | 98.86% | +0.09% | 0.15% |
| bars | bar 1 medium | 1,000,000 | 98.97% | 98.99% | -0.03% | 0.14% |
| tarot | 3 cards | 1,000,000 | 98.86% | 98.94% | -0.08% | 0.17% |
| darts | medium | 1,000,000 | 98.90% | 99.00% | -0.10% | 0.08% |
| sicbo | small | 1,000,000 | 97.17% | 97.22% | -0.05% | 0.10% |
| rps | continue draws | 1,000,000 | 98.50% | 99.00% | -0.50% | 0.10% |
| slide | target 2.16x | 1,000,000 | 99.07% | 99.12% | -0.06% | 0.11% |
| mines | 3 mines, 3 picks | 1,000,000 | 98.99% | 99.00% | -0.01% | 0.07% |
| dragontower | medium | 1,000,000 | 98.91% | 99.00% | -0.09% | 0.15% |
| pump | medium 3 pumps | 1,000,000 | 99.03% | 99.00% | +0.03% | 0.09% |
| chicken | medium 3 lanes | 1,000,000 | 98.97% | 99.00% | -0.03% | 0.07% |
| moles | medium | 1,000,000 | 98.93% | 99.00% | -0.07% | 0.12% |
| snakes | medium 3 rolls | 1,000,000 | 98.99% | 99.00% | -0.01% | 0.09% |
| wheel | 20 seg medium | 1,000,000 | 99.07% | 98.90% | +0.17% | 0.08% |
| roulette | red | 1,000,000 | 97.43% | 97.30% | +0.14% | 0.10% |
| baccarat | banker | 1,000,000 | 99.02% | 98.94% | +0.08% | 0.09% |
| crash | auto 2x | 1,000,000 | 99.04% | 99.00% | +0.04% | 0.10% |
| hilo | 3 guesses | 1,000,000 | 99.03% | 99.00% | +0.03% | 0.62% |
| pharaoh | spin | 200,000 | 98.53% | 99.11% | -0.58% | 0.57% |
| ronin | spin | 200,000 | 98.46% | 99.02% | -0.57% | 0.57% |
| spellbook | spin | 200,000 | 98.40% | 98.97% | -0.58% | 0.57% |
| blackjack | basic strategy | 200,000 | 97.62% | 99.54% | -1.92% | 0.22% |
| videopoker | simple strategy | 200,000 | 97.53% | 99.54% | -2.01% | 0.90% |

Theoretical values are the game's published tables. Blackjack (0.9954) and Video Poker (0.9954)
assume strong play; the simulated strategies are conservative simplifications, so their measured
values are slightly lower and are reported rather than asserted. Roulette (97.30%), Sic Bo (97.22%)
and Baccarat (98.94%) use their standard casino pay tables, as documented in DECISIONS.md.

Run the full spec sample with:

```bash
python -m scripts.rtp_report --rounds 1000000 --slow-rounds 200000
```