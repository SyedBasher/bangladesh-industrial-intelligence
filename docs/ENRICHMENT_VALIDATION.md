# External enrichment validation — v1.3

The DIFE/LIMA registry remains the backbone. External sources add evidence and commercial value, but they do not replace DIFE fields and they do not automatically identify the same physical site.

The v1.3 enrichment engine supports staged records from:

- EPB Exporter Database;
- BGMEA;
- BKMEA;
- BEPZA;
- Department of Environment (DoE/ECC).

## 1. Two separate questions

Every enrichment workflow separates:

1. **Does this external record identify the same organization?**
2. **Does it identify this specific DIFE establishment/site?**

A positive answer to the first does not imply a positive answer to the second.

This is especially important for firms with multiple factories.

## 2. Stable source keys

The engine uses source-native identifiers where the public source exposes them:

| Source | Stable key rule |
|---|---|
| EPB | numeric exporter ID from the public exporter URL |
| BGMEA | numeric public member ID; BGMEA registration number retained separately |
| BKMEA | membership number |
| BEPZA | zone + normalized enterprise name unless a stronger public identifier is available |
| DoE | public Client ID |

Display slugs and page titles are not treated as stable identifiers when a stronger source-native key exists.

## 3. Source scope

Default linkage scopes are conservative:

- **BGMEA**: site-level linkage is allowed when factory/site evidence supports it.
- **EPB**: conditional; factory geography must support a site match, otherwise organization-only.
- **BKMEA**: organization-level by default.
- **BEPZA**: conditional; enterprise/zone presence alone is not a one-to-one DIFE plant match.
- **DoE**: conditional project/site candidate. A search result is not proof of a currently valid environmental clearance certificate.

The engine can cap a source at organization level even when name and geography look strong.

## 4. Transparent evidence

The matching decision records each component separately:

- normalized company-name strength;
- district result;
- upazila result;
- address-token overlap;
- source linkage scope.

The system does not publish a hidden composite confidence score.

Match classes remain:

- `EXACT_SITE`
- `PROBABLE_SITE`
- `ORGANIZATION_ONLY`
- `AMBIGUOUS`
- `NO_MATCH`
- `SOURCE_FEASIBILITY_ONLY`

## 5. No negative inference from absence

An enrichment target begins as `PENDING`.

Failure to find or stage an EPB/BGMEA/BKMEA/BEPZA/DoE record does **not** become:

- not an exporter;
- not an association member;
- not in an EPZ;
- no environmental clearance.

A negative business fact requires an authoritative source that explicitly supports that negative claim. None of the current source profiles allows absence-based negative inference.

## 6. Immutable external versions

External records have a stable source key plus append-only content versions.

If a BGMEA profile changes from 700 to 750 employees, the same source record receives a new version. The previous observation is retained.

External fields never overwrite DIFE observations.

## 7. Validation-sample targeting

The frozen 2,000 establishments are planned separately for each source.

For example:

- BGMEA and BKMEA target the RMG/textile validation family;
- EPB/BEPZA/DoE can target broader industrial families.

Out-of-scope establishments are stored as `OUT_OF_SCOPE`, not `NO_MATCH`.

## 8. Coverage metrics

Coverage is measured separately by source and match type:

- eligible validation establishments;
- external records actually reviewed/linked;
- exact-site matches;
- probable-site matches;
- organization-only links;
- ambiguous cases;
- explicit no-match review outcomes;
- feasibility-only records.

The two primary rates are:

```text
site_match_rate =
  (EXACT_SITE + PROBABLE_SITE) / eligible establishments

any_positive_link_rate =
  (EXACT_SITE + PROBABLE_SITE + ORGANIZATION_ONLY) / eligible establishments
```

These are source-validation metrics. They should not be advertised as national coverage until the full validation exercise supports that interpretation.

## 9. Live automation remains source-specific

Each external source has its own automation/reuse policy status.

The presence of a staged parser does not authorize unattended collection. EPB, BGMEA, BKMEA, BEPZA and DoE must each pass their own source-access review before a live collector is enabled.

## 10. Next empirical step

Once the DIFE 2,000-record sample is populated, enrichment should proceed source by source:

1. plan eligible targets;
2. stage source records;
3. review candidate links;
4. store component evidence;
5. measure source coverage and ambiguity;
6. decide which enriched fields are sufficiently reliable for the commercial product.

The first objective is not maximum coverage. It is to learn which external fields can be attached to physical establishments with defensible evidence.
