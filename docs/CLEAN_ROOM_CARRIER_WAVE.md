# Clean Room Carrier Wave v1

Status: FROZEN PHASE-1 MATHEMATICAL BASELINE
Evidence class: G0 / model definition only

## 1. Coordinate spaces

Hierarchical refinement class:
- c=0: W12 = Z_12
- c=1: W36 = Z_12 × Z_3
- c=2: W72 = Z_12 × Z_3 × Z_2 ≅ Z_12 × Z_6

Acoustic/register coordinate:
- g ∈ Z

12-position angular address:
- p ∈ Z_12

Ternary refinement:
- τ ∈ Z_3

Binary refinement:
- β ∈ Z_2

Six-phase coordinate:
- φ = 2τ + 3β (mod 6)

Exact acoustic residual:
- ρ ∈ R, measured in octaves relative to the nominal 12-grid.

A full fine-grained state is:
S = (c,g,p,τ,β,ρ)
or, at c=2,
S = (c,g,p,φ,ρ).

## 2. Exact acoustic coordinate

Let
x = g + p/12 + ρ.

x is logarithmic acoustic position in octave units.

The cylindrical embedding is:
θ = 2π frac(x)
z = floor_nominal(x) / generation index as carried by (g,p)
with ρ preserving exact displacement from the nominal 12-address lattice.

The 12-position wheel is therefore only the nominal angular carrier.
ρ must never be discarded when exact closure matters.

## 3. Complementary acoustic operators

Define:

α = log2(3/2)
βa = log2(4/3)

Then:
α + βa = 1.

Nominal 12-grid decomposition:

α = 7/12 + δ
βa = 5/12 - δ

where:

δ = log2(3/2) - 7/12
  ≈ 0.0016291673878 octaves
  ≈ 1.955000865 cents.

Define operator R:
- x -> x + α
- nominally p -> p + 7 (mod 12)
- carry into g when p crosses 12
- ρ -> ρ + δ
- φ unchanged

Define operator L:
- x -> x + βa
- nominally p -> p + 5 (mod 12)
- carry into g when p crosses 12
- ρ -> ρ - δ
- φ unchanged

Mirror orientation is obtained by reversing the nominal angular direction; all checksum relations remain invariant.

## 4. Primary acoustic checksum

Because α+βa=1:

R followed by L, or L followed by R, gives:

Δg = +1
Δp = 0
Δρ = 0
Δφ = 0.

Thus:

R∘L = L∘R = O

where O is exact one-generation/octave descent with local angular return.

This is the core rule:

LOCAL ADDRESS CLOSURE + GLOBAL GENERATION CHANGE.

## 5. Twelve-step nonclosure checksum

Twelve repeated R operations give:

12α = 7 + κ

where:

κ = log2((3/2)^12 / 2^7)
  = log2(531441/524288)
  ≈ 0.01955000865 octaves
  ≈ 23.46001038 cents.

Therefore:

R^12:
Δp = 0
Δg = +7
Δρ = +κ.

It returns to the same nominal 12-address but NOT the same exact state.

Likewise:

L^12:
Δp = 0
Δg = +5
Δρ = -κ.

And:

R^12 L^12:
Δp = 0
Δg = +12
Δρ = 0.

So the clean room contains both:
- exact complementary closure under R+L;
- spiral nonclosure under twelve same-direction fifth/fourth traversals.

## 6. Ternary/binary refinement

At c=0:
W12 = Z_12.

Ternary refinement:
E3: Z_12 -> Z_12 × Z_3.

For each p:
(p) expands to
(p,0), (p,1), (p,2).

Thus:
|W36| = 12×3 = 36.

Binary refinement:
E2: Z_12 × Z_3 -> Z_12 × Z_3 × Z_2.

For each (p,τ):
(p,τ) expands to
(p,τ,0), (p,τ,1).

Thus:
|W72| = 12×3×2 = 72.

Equivalent six-phase form:
W72 ≅ Z_12 × Z_6.

## 7. Six-phase operators

Encode:
φ = 2τ + 3β mod 6.

Ternary rotation T:
τ -> τ+1 mod3
therefore:
φ -> φ+2 mod6.

Binary flip B:
β -> β+1 mod2
therefore:
φ -> φ+3 mod6.

Checksums:

T^3 = identity
B^2 = identity
TB = BT.

The natural binary fibers at fixed τ are:
{φ, φ+3}.

The natural ternary fibers at fixed β are:
{φ, φ+2, φ+4}.

Every one of the six phase states is uniquely specified by one ternary coordinate and one binary coordinate.

## 8. Independence of axes

Acoustic operators R,L,O act on:
(g,p,ρ)

and must not alter:
(τ,β,φ)

unless a later model explicitly defines a coupling operator.

Phase operators T,B act on:
(τ,β,φ)

and must not alter:
(g,p,ρ).

Refinement maps E3,E2 change class resolution c and add coordinates; they do not silently move existing acoustic coordinates.

Any topology that requires an undeclared simultaneous jump across independent axes is illegal.

## 9. Legal forward/reverse moves

Forward:
W12 --E3--> W36 --E2--> W72

Reverse projections:
π2: (p,τ,β) -> (p,τ)
π3: (p,τ) -> p.

Reverse acoustic operators:
R^-1 and L^-1 subtract α and βa exactly, including residual.

Reverse phase operators:
T^-1 = T^2
B^-1 = B.

No reverse reconstruction may invent a discarded coordinate; if projection erased τ or β, reversal yields a set of possible preimages, not one preferred answer.

## 10. Closed-path checksums

A valid path may be tested by its net tuple:

C(path) = (Δg, Δp, Δτ, Δβ, Δρ).

Examples:

R L:
(+1, 0, 0, 0, 0)

R^12:
(+7, 0, 0, 0, +κ)

L^12:
(+5, 0, 0, 0, -κ)

T^3:
(0,0,0,0,0)

B^2:
(0,0,0,0,0)

R^12 L^12:
(+12,0,0,0,0)

A proposed topology fails if its claimed closed path produces an unaccounted nonzero checksum.

## 11. Carrier-wave invariants

I1. 12 parent addresses.
I2. Each parent admits 3 ternary refinements.
I3. Each ternary refinement admits 2 binary states.
I4. 12×3×2 = 72 fine addresses.
I5. The 6-state local fiber is exactly Z3×Z2 ≅ Z6.
I6. Complementary acoustic operators close locally while advancing one global generation.
I7. Repeated same-direction 12-step traversal returns nominally but carries a nonzero residual κ.
I8. Exact residuals cannot be erased to force closure.
I9. Independent axes cannot be crossed without a declared coupling operator.
I10. Projection loses information; inversion of a lossy projection returns a preimage set, not a unique reconstruction.

## 12. Phase-2 admissibility test

For any textless candidate topology, evaluate:

1. Can every edge be assigned a declared operator?
2. Does every closed path satisfy its checksum?
3. Are class changes legal refinements/projections?
4. Are any missing coordinates being silently invented?
5. Does the topology preserve 12→36→72 cardinality?
6. Does it preserve ternary/binary fiber structure?
7. Does it preserve exact acoustic residuals?
8. Can it be run both forward and backward without changing the operator definitions?

Outcome:
- PASS
- FAIL
- UNDERDETERMINED / NO CALL

No historical or semantic material may alter these rules during quarantine.
