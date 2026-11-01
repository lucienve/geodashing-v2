# Spatial-Statistical Review of "The Distribution of Geodashing Dashpoints" (2011)

## 1. Overview & Historical Context

In May 2011—just ahead of Geodashing's 10th anniversary—a Geodashing player and
university Geographic Information Analysis student writing under the handle
**Wisk** authored
[The Distribution of Geodashing Dashpoints](./The%20Distribution%20of%20Geodashing%20Dashpoints.pdf).
At the time, little academic literature existed on location-based GPS games, and
a lively, recurring question among Geodashing's ~739 players worldwide was
whether monthly dashpoints were truly random or whether certain areas tended to
receive clusters of points over time.

To investigate this question empirically, the author assembled a substantial
historical dataset using 2011 desktop tools: downloading 119 monthly archives
(roughly 32,000 WGS-84 coordinate pairs per game, or ~3.8 million global points
in total), writing custom Microsoft Excel macros to extract points around the
state of Arizona, projecting the coordinates to `NAD_1983_UTM_Zone_12N`,
clipping them to a 20 km buffer around Arizona, and evaluating three temporal
slices in ArcGIS:

- **Single Month (`May 2011`):** 88 dashpoints from a single game.
- **Three-Year Window (`2007–2010`):** 3,174 dashpoints pooled across 36 games.
- **All Games (`2001–2011`):** 9,861 dashpoints pooled across 119 games.

_(Note: Exact point counts $N$ above are derived directly from the
Observed/Expected Average Nearest Neighbor metrics reported in Figure 4 of the
paper via $N = 0.25 \cdot A / D_E^2$.)_

The paper also preserves an invaluable contemporary description from
Geodashing's creator, Scout, explaining the original "stepping/grid" generation
process: starting at a predefined waypoint in Alaska, generating random offsets
for a candidate dashpoint, stepping due east by a fixed distance in kilometers
around a latitude band, then stepping due south to repeat the process down to
New Zealand—enforcing a minimum neighbor distance within each game and
discarding points that fell on water.

This review evaluates the paper's empirical data, statistical methods, and
conclusions alongside modern spatial point-process theory and Geodashing V2's
grid generator ([`generate_game.py`](../backend/scripts/generate_game.py)).

### Summary of Reported Metrics (Figure 4, Average Nearest Neighbor)

| Dataset     | Derived Points ($N$) | Observed Mean $D_O$ (m) | Expected Mean $D_E$ (m) | Ratio ($R = D_O / D_E$) | $z$-Score | Reported Study Area ($A$, $\text{km}^2$) |
| :---------- | -------------------: | ----------------------: | ----------------------: | ----------------------: | --------: | ---------------------------------------: |
| `May 2011`  |                   88 |               39,732.06 |               30,959.44 |                1.283359 |  +5.08521 |                               337,307.38 |
| `3 Years`   |                3,174 |                4,961.29 |                5,268.15 |                0.941750 |  -6.27810 |                               352,357.89 |
| `All Games` |                9,861 |                2,803.67 |                2,997.95 |                0.935195 | -12.31118 |                               354,511.92 |

---

## 2. Are the Paper's Findings Consistent with the Data?

### Single-Month Data (`May 2011`) — Consistent

For an individual monthly game, the paper's findings are fully consistent with
both the underlying data and Scout's generation algorithm:

- **Average Nearest Neighbor (ANN):** The observed mean nearest-neighbor
  distance (39.73 km) is 28.3% larger than expected under Complete Spatial
  Randomness (CSR) (30.96 km), yielding $R = 1.283$ and $z = +5.09$ ($p <
  0.01$).
- **Ripley's K Function ($L(d)$):** Shows statistically significant spatial
  dispersion at distances below 67 km.

Both metrics accurately capture the geometry of the grid/stepping algorithm.
Placing roughly one point per ~60 km step while enforcing a minimum separation
distance (~12 km) creates an **inhibited (stratified / hard-core) spatial point
process**. Within any single month, points actively repel one another at scales
below the ~60–67 km cell spacing.

### Multi-Year Pooled Data (`3 Years` and `All Games`) — Internally Inconsistent

When evaluating the pooled multi-year datasets, the paper's two primary
quantitative tests point in opposite directions on the exact same coordinates:

1. **Ripley's K Function (Figure 3, p. 5) indicates dispersion, not
   clustering:** In ArcGIS's `L(d)` transformation of Ripley's K, values where
   the **Observed** curve (red) lies _above_ the **Expected** line (blue)
   indicate clustering, whereas values where **Observed** lies _below_
   **Expected** indicate dispersion. In Figure 3, the red Observed line remains
   _below_ the blue Expected line across the entire distance range for
   `May 2011`, `3 Years`, and `All Games`. The author candidly notes in the text
   that the multi-year Ripley's K results _"tended towards dispersion"_, yet
   sets this aside in the final conclusion.
2. **Average Nearest Neighbor (Figure 4, p. 6) reports mild clustering:** ANN
   reports $R = 0.9418$ ($z = -6.28$) for `3 Years` and $R = 0.9352$ for
   `All Games` ($z = -12.31$). While the negative $z$-scores appear dramatic,
   the physical difference between observed and expected nearest-neighbor
   distances in `All Games` is quite small: 2,804 m observed vs. 2,998 m
   expected (a difference of 194 m, or ~6.5%).

Because a dataset cannot simultaneously be globally dispersed and globally
clustered at overlapping scales without a structural reason, this divergence is
a helpful clue pointing toward a subtle parameter difference between how the two
ArcGIS tools measured the study area.

---

## 3. Are the Paper's Conclusions Accurate?

The paper's first conclusion—that **individual monthly games are strongly
dispersed**—is completely accurate and well demonstrated.

However, the broader conclusion—that **geographic clustering increases over
time**, creating persistent high-density advantage zones and low-density
disadvantage zones—does not follow from the reported statistics for two main
reasons:

### 1. Effect Size ($R$) vs. Sample-Size Significance ($z$-Score)

Comparing `3 Years` ($N = 3,174$) to `All Games` ($N = 9,861$), the Nearest
Neighbor Ratio $R$—which measures the actual _degree_ of clustering—barely
changes at all (`0.9418` vs. `0.9352`, a shift of less than 0.7%).

The $z$-score nearly doubles from `-6.28` to `-12.31` not because dashpoints
became more clustered over time, but because the ANN test statistic scales with
the square root of the total point count $N$:

$$z = \frac{R - 1}{0.52272}\sqrt{N}$$

Whenever a dataset carries a constant ~6% offset in $R$ (due to study-area
geometry or water exclusions, discussed in Section 4), increasing the sample
size by $3.1\times$ automatically multiplies $|z|$ by $\sqrt{3.1} \approx
1.76\times$. It is very common in introductory spatial statistics to read a
growing $|z|$-score as "stronger clustering," when it actually reflects higher
statistical power detecting the exact same ~6% baseline offset.

### 2. Superposition of Independent Monthly Point Processes

At first glance, seeing $z$ swing from `+5.09` (1 month) to `-6.28` (36 months)
looks like a dramatic reversal in behavior. From a point-process perspective,
however, the loss of dispersion across pooled games is expected:

- The minimum neighbor distance rule only prevents collisions **within the same
  month's game**. Each new month is generated independently of prior months.
- When 36 or 119 independent games are stacked together, the average distance to
  the nearest neighbor drops to 2.8–5.0 km—well below the single-month ~60 km
  grid spacing and ~12 km minimum separation. Thus, a point's nearest neighbor
  in the pooled dataset almost always comes from a _different_ month.
- By spatial point-process superposition theory, stacking many independent
  realizations of an inhibited grid process erases single-game short-range
  repulsion ($R = 1.28$), causing the pooled points to converge toward Complete
  Spatial Randomness ($R \approx 1.00$) across the valid dry-land domain.

---

## 4. GIS Tooling Nuances & Methodological Details

Working with ArcGIS 10's Spatial Statistics toolbox involved several well-known
user-interface subtleties that explain why the multi-year tools disagreed:

### 1. Default Study Area Behavior in ArcGIS Average Nearest Neighbor

In the Methods section (p. 3), the author carefully clipped all datasets to a 20
km buffer around Arizona and passed that buffer polygon as the
`Study Area Feature` in the **Ripley's K Function** tool.

However, ArcGIS's **Average Nearest Neighbor** tool does not accept a polygon
layer for its study area; instead, it has an optional numeric `Area` field. When
that optional field is left blank, ArcGIS automatically falls back to computing
the area of the **Minimum Enclosing Rectangle** (bounding box) around the input
points. We can see this directly in Figure 4's `Study Area` metadata, which
grows slightly as more points fill out the corners of the polygon:

- `May 2011` ($N = 88$): `337,307.38` $\text{km}^2$
- `3 Years` ($N = 3,174$): `352,357.89` $\text{km}^2$
- `All Games` ($N = 9,861$): `354,511.92` $\text{km}^2$

Because Arizona's western and southwestern boundaries follow the Colorado River
and the diagonal Mexican border near Yuma, a large triangular wedge of the
minimum bounding rectangle lies _outside_ the clipped study polygon and contains
zero points. As a result, the Minimum Enclosing Rectangle (~354,512
$\text{km}^2$) is roughly **13–14% larger** than the actual clipped study
polygon (~310,000 $\text{km}^2$).

In the ANN expected-distance equation:

$$D_E = \frac{0.5}{\sqrt{N / A}}$$

overstating the valid placement area $A$ by ~13.5% artificially inflates the
expected distance $D_E$ by $\sqrt{1.135} \approx 1.065$ (+6.5%). Consequently,
even a **perfectly uniform random point pattern** inside the clipped Arizona
polygon will yield an apparent Nearest Neighbor Ratio of:

$$R = \frac{D_O}{D_E} \approx \frac{1}{1.065} \approx 0.939$$

This bounding-box fallback alone accounts for nearly the entire reported ratio
in `3 Years` ($R = 0.9418$) and `All Games` ($R = 0.9352$). Supplying the true
clipped dry-land area (~310,000 $\text{km}^2$) lowers $D_E$ in `All Games` from
2,998 m to ~2,803 m, matching the observed 2,804 m ($R \approx 1.00$, $z \approx
0$).

### 2. Point Density Kernel Scaling and Boundary Edge Effects (Figure 5)

ArcGIS's **Point Density** tool creates a smoothed visualization raster rather
than a formal hypothesis test, and two visual effects make multi-year maps look
clustered even under uniform randomness:

- **Neighborhood radius vs. point spacing:** With ArcGIS's default neighborhood
  search radius (~18 km for an Arizona-sized extent), `May 2011` ($N = 88$, mean
  spacing ~40 km) has at most 1 point per search circle, rendering isolated pale
  dots. In `3 Years` and `All Games`, dozens of points fall inside each search
  circle, and ArcGIS automatically stretches the blue color ramp between the
  minimum and maximum local counts—visually emphasizing ordinary random Poisson
  fluctuations.
- **Clip-boundary halo:** Along the outer rim of the buffered Arizona polygon in
  Figure 5 (`3 Years` and `All Games`), density drops to white/pale blue. This
  occurs because search circles near the boundary extend partially outside the
  clipped dataset (where point count is zero), cutting computed edge density
  roughly in half and making the interior of the state look like a large central
  cluster by contrast.

### 3. Manual Excel Re-Plotting of Ripley's K (Figure 3)

The author notes (p. 4) that ArcGIS's `Display Results Graphically` checkbox
failed to render a chart—a notoriously frustrating bug in ArcGIS 10—requiring
the output table to be re-plotted manually in Excel. Two small artifacts slipped
in during that manual export:

- The horizontal axis in Figure 3 plots the Excel row numbers (`1` through `10`,
  representing the 10 distance bands) rather than the actual distance values in
  meters, while the vertical axis plots `L(d)` in meters (`0` to `160,000`).
- In `gd3years` and `gdallgames`, the narrow dotted lines (`Min L(d)` and
  `Max L(d)` from the 9 Monte Carlo permutations) hug the blue `Expected` line,
  while the red `Observed` curve falls below `Min L(d)` at larger bands. In
  Ripley's K, falling below `Min L(d)` indicates statistically significant
  _dispersion_ at those distances rather than non-significance.

---

## 5. Why Clustering (Apparent or Real) Could Occur

Even though the negative ANN $z$-scores in the paper are largely explained by
the bounding-box area calculation, it is still worth asking: **Are there real
geographic or algorithmic reasons why dashpoints in the original game would
cluster over time—or feel clustered to players?** Yes, several interesting
mechanisms apply.

### A. Study-Area Water Exclusions (Inhomogeneous Placement Domain)

In Geodashing, candidate points landing on water are discarded. Within Arizona
and its 20 km buffer, major reservoirs and border water bodies—including Lake
Powell, Lake Mead, Lake Mohave, Lake Havasu, and Theodore Roosevelt Lake—form
permanent voids that never receive dashpoints across all 119 games. Testing
dry-land-only points against a null hypothesis of uniform randomness across an
unmasked polygon (land + water) naturally makes the points on dry land measure
as slightly more concentrated than total surface area alone would predict.

### B. Potential Fixed-Grid Mechanics in Scout's Original Algorithm

In Figure 5 (`All Games` Point Density, p. 6), a closer look at the interior of
Arizona shows a subtle, quasi-regular lattice of roughly 80–90 darker blue spots
spaced ~60 km apart—remarkably close to the ~88 dashpoints generated per game in
that region. Scout's description quoted on page 2 suggests how a subtle periodic
pattern could genuinely arise in the original generator:

> _"Starting in Alaska at some predefined waypoint, random offsets are generated
> to randomize a dashpoint location. Then a waypoint is projected due east at
> some predefined distance, measured in kilometers, not in longitude... Then,
> another waypoint is projected due south and start the stepping east and
> randomize operation all over again."_

1. **Fixed Anchor Grid Across Months:** If the original script began at the
   **exact same predefined waypoint in Alaska** every month and stepped south
   and east by a fixed kilometer increment, then the underlying skeleton of base
   waypoints remained stationary from month to month. Over 119 games, a
   stationary base grid only produces a perfectly flat long-term density if the
   random offsets tile the sphere into exact, non-overlapping, gapless spherical
   trapezoids:
   - **Polar `(distance, bearing)` offsets:** In early GPS waypoint utilities,
     randomizing a location from a base waypoint was often implemented by
     picking a uniform random bearing $\theta \in [0^\circ, 360^\circ)$ and a
     uniform random distance $r \in [0, R_{\max}]$. Because circle circumference
     grows with $2\pi r$, uniform radial sampling concentrates probability
     density near $r = 0$ ($\rho(r) \propto 1/r$), creating a gentle bullseye of
     higher multi-year density around every fixed base waypoint. Even with
     area-corrected disk sampling ($r \propto \sqrt{u}$), circular neighborhoods
     cannot tile a 2D plane without either leaving low-density corner gaps
     between four circles or creating higher-density lens overlaps between
     adjacent circles.
   - **Step size vs. rectangular offset mismatch:** Even with rectangular
     latitude/longitude offsets, if the maximum offset radius was slightly
     smaller or larger than half the step distance, 119 pooled games would form
     a subtle periodic grid of higher-density zones and lower-density seams.
   - _(Comparison with Geodashing V2: In
     [`generate_game.py`](../backend/scripts/generate_game.py),
     `build_spherical_grid()` avoids stationary grid nodes by applying a fresh
     random latitude shift `lat_shift` and independent per-band random longitude
     offsets `lon_offset` on every game run, while `sample_point_in_cell()` uses
     $\arcsin$-weighted area-uniform sampling across each spherical trapezoid.)_

2. **Sequential Minimum-Distance Rejection Skew:** Because the original
   algorithm stepped west-to-east and north-to-south while testing each new
   candidate against already-placed neighbors (~12 km minimum spacing), a cell's
   western and northern margins were already constrained by the preceding points
   in the sweep, subtly nudging accepted retries slightly eastward and southward
   within contested cells.

3. **Coastal Water Redistribution (Outside Landlocked Regions):** In coastal
   regions (though less applicable to Arizona), algorithms that redistribute
   water hits to neighboring land cells—such as Pass 2 in V2's
   `generate_grid_dashpoints()`—intentionally produce roughly $2\times$ higher
   dashpoint density along coastlines compared to deep continental interiors.

### C. Player Experience: Road Accessibility & the 2D Birthday Paradox

Wisk began the paper with an authentic player observation: why do dashpoints
month-to-month so often seem to land near previously scored points? Two human
and geometric factors reinforce that impression even when points are uniform:

- **The 2D Spatial Birthday Paradox:** Once 9,861 historical dashpoints exist in
  the Arizona study region, the average distance from _any_ random spot to the
  nearest historical dashpoint is under 3 km. In a new month of 88 points, it is
  statistically near-certain that several new dashpoints will land within 1–2 km
  of memorable historical dashpoints purely by chance.
- **Road-Network Selection Bias:** Players can primarily reach and score
  dashpoints located near drivable road corridors and accessible public land.
  Because Arizona's road network is itself tightly clustered along valleys and
  interstates, the subset of _visited and discussed_ dashpoints is genuinely
  clustered, even when remote backcountry dashpoints are evenly spread.

---

## 6. What Additional Data & Analyses Would Be Useful?

To build on Wisk's 2011 study and definitively test whether the original
2001–2011 dashpoint archives contained stationary grid hotspots, the following
data and analyses would be especially informative:

1. **Exact Terrestrial (Dry-Land) Study Area Polygon:** Computing the exact area
   (in $\text{m}^2$) of the buffered Arizona clip polygon _minus_ excluded lakes
   and reservoirs, and passing that exact numeric area into the Average Nearest
   Neighbor tool (as well as using an inhomogeneous land mask for Monte Carlo
   permutations).
2. **Modulo / Phase-Folded Coordinate Analysis:** Taking all 119 historical
   games and folding point latitudes and longitudes modulo the ~60.05 km
   ($\approx 0.54^\circ$) grid step size—or computing a 2D spatial periodogram /
   Fourier transform. If the original generator used a fixed starting anchor in
   Alaska with polar or non-tiling offsets, phase folding would immediately
   reveal a sharp periodic peak at the ~60 km step wavelength; if the origin was
   randomized monthly, the phase histogram would be flat.
3. **Intra-Game vs. Inter-Game Pair-Correlation Function $g(r)$:** Unlike
   cumulative Ripley's $K(r)$ (which integrates all pairs from $0$ to $r$,
   blending short- and long-range effects together), computing the
   non-cumulative **pair-correlation function $g(r)$** separately for
   _same-month pairs_ vs. _cross-month pairs_ (with border edge correction)
   would cleanly separate within-month ~12 km repulsion from any cross-month
   clustering around fixed grid centers.
4. **Multi-Region Coastal vs. Inland Comparisons:** Repeating the analysis
   across a flat, lake-free interior plain (e.g., Kansas) and a complex
   coastline (e.g., California or Florida) to isolate coastline and water-mask
   effects from core grid-stepping behavior.
5. **Original Generator Source Parameters & Visited-Point Logs:** Comparing _all
   generated dashpoints_ against _scored dashpoints_ alongside archived
   parameters from Scout's original script (specifically whether the Alaska
   origin was fixed or jittered monthly, how random offsets were drawn, and
   which land/water mask dataset was used between 2001 and 2011).

---

## 7. Summary Appreciation

Viewed in its 2011 context, Wisk's paper is a thoughtful, well-motivated piece
of community scholarship that preserved Scout's description of the original
Geodashing algorithm, correctly proved and quantified single-month spatial
dispersion, and assembled a decade-long spatial archive to test player folklore
with real GIS tools. With minor adjustments for ArcGIS's default bounding-box
area calculation and point-process superposition across independent months, the
paper's dataset tells a clear, coherent story—and even hints at subtle
fixed-grid geometry worth exploring in historical Geodashing archives.
