# Graph Guide: Intelligent Test Input Generation Using AI for Improving Random Testing Effectiveness

**Study:** Intelligent Test Input Generation Using AI for Improving Random Testing Effectiveness  
**Benchmark Target:** BugsInPy `youtube-dl` Bug 1 (`youtube_dl.utils._match_one`)  
**Comparison:** Genetic Algorithm (GA) vs. Pure Seeded Random Testing  
**Evaluation Scope:** 10 Independent Seed-Paired Runs, 200 Inputs per Method/Run (4,000 Total Inputs)

---

## 1. Primary Evaluation Graphs

### 1.1 [`coverage_comparison.png`](./coverage_comparison.png)
- **Description:** Direct comparison of target-function Statement (Line) Coverage (%) and Branch Coverage (%) between Pure Random Testing and AI-Guided GA across 10 paired seeds.
- **Key Findings:**
  - **Line Coverage:** Random achieves **69.70%** (23/33 statements), whereas GA achieves **84.85%** (28/33 statements) — a **+15.15 percentage point** improvement ($p = 0.00098$, statistically significant).
  - **Branch Coverage:** Random reaches **56.25%** (9/16 branches), whereas GA reaches **75.00%** (12/16 branches) — a **+18.75 percentage point** improvement.
- **Why GA Outperforms:** GA uses branch distance and boundary condition guidance to systematically trigger unreached branches (including syntax error handlers, filesize suffixes, and none-inclusive operators) that random testing repeatedly misses.

### 1.2 [`fault_detection_comparison.png`](./fault_detection_comparison.png)
- **Description:** Dual-panel analysis of bug detection effectiveness:
  - **Panel (A):** Mean Fault Exposure Rate (% of generated test cases that reveal the defect).
  - **Panel (B):** Mean Total Fault-Revealing Test Cases Discovered per 200-input run.
- **Key Findings:**
  - **Exposure Rate:** GA achieves **15.55%** vs. Random at **4.20%** — a **3.65× higher bug revelation rate** ($p < 0.001$).
  - **Defect Discovery Yield:** GA generates **31.1 bug-revealing tests** per run vs. Random at **8.4 tests** (+22.7 extra defect disclosures).
  - **Fault Exposure Reliability:** GA exposed the regression defect in **100% of runs (10 out of 10 seeds)**.

### 1.3 [`generation_overhead_comparison.png`](./generation_overhead_comparison.png)
- **Description:** Computational overhead and search efficiency trade-off:
  - **Panel (A):** Milliseconds spent in candidate generation vs. target function execution.
  - **Panel (B):** Search Cost-Benefit Ratio (Faults Discovered per CPU Generation Second).
- **Key Findings:**
  - Generation overhead for GA is **0.065 s** (~0.32 ms/candidate) vs. Random at **0.025 s** (~0.12 ms/candidate).
  - Search Efficiency: GA yields **479.2 faults/second** of generation time vs. Random at **335.3 faults/second**.
  - **Takeaway:** The tiny microsecond algorithmic overhead of GA selection, crossover, and mutation is overwhelmingly repaid by its 3.65× higher bug-finding power.

### 1.4 [`coverage_progression.png`](./coverage_progression.png)
- **Description:** Cumulative Line Coverage growth trajectory over the 200-input evaluation sequence.
- **Key Findings:**
  - Random testing plateaus prematurely at **69.70%** after ~20 test cases due to high input redundancy.
  - GA continuously breaks through plateaus, reaching >70% coverage within 25 evaluations and climbing to **84.85%** final coverage as mutation navigates deep conditional branches.

### 1.5 [`fault_detection_progression.png`](./fault_detection_progression.png)
- **Description:** Cumulative fault discovery curves over test evaluations (1 to 200).
- **Key Findings:**
  - **Time-to-First-Bug:** GA isolates the regression defect early (average test #9), whereas Random requires on average ~42 test evaluations.
  - **Discovery Slope:** GA steadily accumulates defect-revealing inputs throughout execution.

---

## 2. Master Evaluation Dashboard

### [`comprehensive_evaluation_dashboard.png`](./comprehensive_evaluation_dashboard.png)
- **Description:** A publication-grade 4-panel master figure synthesizing:
  - **(A) Code & Branch Coverage Achievement**
  - **(B) Defect Detection Rate & Yield**
  - **(C) Dynamic Coverage Growth Trajectory**
  - **(D) Computational Cost-Benefit Trade-off**
- Formatted with 300 DPI high resolution, high-contrast accessible palettes, and annotated confidence intervals for direct inclusion in the term paper and presentation.
