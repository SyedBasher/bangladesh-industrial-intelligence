# Typed intelligence observations — v1.7

External source profiles are first retained exactly as source records and versions. The v1.7 layer then extracts selected high-value fields into typed observations for search, analytics and the product interface.

The typed layer does **not** replace the raw source fields.

## 1. Initial typed fields

### BGMEA

Site-scoped when the public profile exposes them:

- employment count;
- machine count;
- production capacity;
- principal products;
- certifications.

Organization-scoped:

- BGMEA membership-record evidence;
- BGMEA registration;
- EPB registration when displayed;
- export markets.

### EPB

Organization-scoped:

- exporter-database-record evidence;
- HS codes;
- products;
- export markets;
- association;
- EPB/export registration;
- exporter category.

EPB exporter presence is recorded as **exporter-database evidence**, not as proof of current shipment activity.

## 2. Scope is part of the data model

Every typed observation has one of two scopes:

- `SITE`
- `ORGANIZATION`

This is not a display convention. It controls whether an observation can propagate through an entity link.

## 3. Propagation rule

For an `EXACT_SITE` or `PROBABLE_SITE` link:

- site observations may be attached to the DIFE establishment;
- organization observations may be shown with the establishment but remain explicitly organization-scoped.

For an `ORGANIZATION_ONLY` link:

- organization observations may be shown;
- site observations are blocked.

Therefore an organization-level BGMEA match cannot assign the source's employee count, machine count or factory capacity to a DIFE plant.

## 4. No scope laundering

An organization observation remains organization-scoped even when the organization has only one known factory.

For example, an EPB record with HS codes 6109 and 6110 can be shown on a linked establishment profile as organization evidence, but the product must not state that the specific factory produced or exported those HS codes unless another source supports that site-level conclusion.

## 5. Numeric parsing

Counts are retained both as raw source text and, when possible, a parsed numeric value.

Examples:

```text
Employees: "1,250"
→ value_numeric = 1250

Production Capacity: "2.5 million pcs/year"
→ value_numeric = 2,500,000
→ unit = "pcs/year"
```

The raw label and raw value are always preserved.

## 6. Multi-valued fields

Products, markets, certifications and HS codes can generate multiple typed observations from one source field.

The original raw field remains stored in the external record version, so the split representation is auditable.

## 7. Versioning

Typed observations belong to a specific immutable external record version.

If a source profile later changes from:

```text
Employees: 1,200
```

to:

```text
Employees: 1,350
```

both source versions and both typed observations remain in history.

A refreshed source record must pass entity resolution again before its new site-scoped observations are propagated to the establishment profile.

## 8. Product-facing profile

The private store can now return one establishment intelligence profile containing:

- DIFE identity and geography;
- latest validated external link per source;
- typed intelligence grouped by observation type;
- source name;
- match type;
- source scope;
- site-attributable flag;
- raw value;
- parsed value/unit;
- source-reported update text;
- retrieval timestamp.

This is the contract that a future API/frontend can consume.

## 9. Next step

The next layer should create a **safe product-export/API view** from these private profiles.

That layer should expose only approved fields and calculated indicators, exclude raw private snapshots, and provide a compact JSON contract for the web interface. It will also be the right place to add higher-order measures such as establishment scale bands, export-evidence breadth and source-consistency flags.
