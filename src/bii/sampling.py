from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


SECTOR_TARGETS: tuple[tuple[str, str, int, tuple[str, ...]], ...] = (
    ("RMG_TEXTILE", "RMG & textiles", 500, (
        "গার্মেন্টস/তৈরি পোশাক", "কটন টেক্সটাইল", "হোসিয়ারী", "এমব্রয়ডারী", "এক্সেসরিজ (গার্মেন্টস)",
    )),
    ("FOOD_AGRO", "Food & agro-processing", 300, (
        "ফুড ইন্ডাষ্ট্রিজ", "ব্রেড এন্ড বিস্কুট", "মিষ্টান্ন কারখানা", "রাইস মিল", "ফ্লাওয়ার মিল", "অয়েল মিল",
        "ডাল মিল", "মসলা মিল", "এগ্রো প্রোডাক্টস", "ফিড মিল", "দুগ্ধ প্রক্রিয়াজাতকরণ", "মৎস্য প্রক্রিয়াজাতকরণ",
        "মিট প্রসেসিং", "চিনি কারখানা", "বেভারেজ ইন্ডাষ্ট্রিজ", "চিলিং সেন্টার", "হিমাগার",
    )),
    ("PHARMA_CHEM_PLASTIC", "Pharma, chemicals & plastics", 250, (
        "ফার্মাসিউটিক্যালস", "কেমিক্যাল ইন্ডাষ্ট্রিজ", "প্লাস্টিক কারখানা", "পেস্টিসাইড কারখানা",
        "ফার্টিলাইজার/সার কারখানা", "রাবার ইন্ডাস্ট্রিজ", "সাবান কারখানা", "কসমেটিক্স কারখানা",
        "ব্যাটারী কারখানা", "ড্রাইসেল কারখানা",
    )),
    ("ENGINEERING_MATERIALS", "Engineering, steel & construction materials", 250, (
        "ইঞ্জিনিয়ারিং", "স্টীল মিল", "রি-রোলিং", "ফাউন্ড্রি/মেটাল", "সিমেন্ট কারখানা", "সিরামিকস কারখানা",
        "গ্লাস এন্ড সিলিকেট কারখানা", "মার্বেল কারখানা", "ইটভাটা/ব্রিকস ফিল্ড", "ক্যাবল কারখানা", "এ্যালুমিনিয়াম কারখানা",
    )),
    ("LEATHER_FOOTWEAR", "Leather & footwear", 150, ("ট্যানারী", "চামড়াজাত দ্রব্য", "ফুটওয়্যার")),
    ("LOGISTICS_WAREHOUSE", "Logistics, warehousing & transport", 150, (
        "ডিপো/গুদাম/ভান্ডার", "কনটেইনার ডিপো", "লজিস্টিক্স কোম্পানী", "ফ্রেইট ফরোয়ার্ড", "কুরিয়ার সার্ভিস",
        "পণ্য ডেলিভারী প্রতিষ্ঠান", "সড়ক পরিবহন", "নৌ পরিবহন", "বিমান পরিবহন", "সমুদ্র বন্দর", "নৌ বন্দর", "স্থল বন্দর",
    )),
    ("ELECTRICAL_ELECTRONICS", "Electrical & electronics", 100, (
        "ইলেকট্রনিক্স কারখানা", "ইলেকট্রিকস কারখানা", "বিদ্যুৎ-পাওয়ার স্টেশন", "মোবাইল অপারেটর", "ইন্টারনেট সেবাদানকারী",
    )),
    ("OTHER_MANUFACTURING", "Other manufacturing", 200, (
        "বিবিধ কারখানা", "বিবিধ শিল্প প্রতিষ্ঠান", "প্রিন্টিং এন্ড প্যাকেজিং", "পেপার মিল", "বোর্ড মিল", "জুট মিল",
        "ফার্ণিচার কারখানা", "শিপইয়ার্ড", "শিপ ব্রেকিং", "তামাক প্রক্রিয়াকরণ", "সিগারেট কারখানা", "বরফ কল",
    )),
    ("NON_FACTORY_CONTROL", "Non-factory establishments (control group)", 100, (
        "বিবিধ বাণিজ্য প্রতিষ্ঠান", "বাণিজ্যিক ব্যাংক", "বীমা প্রতিষ্ঠান", "সুপার শপ", "রেস্তোঁরা", "হাসপাতাল",
        "ডায়াগনস্টিক সেন্টার", "ফার্মেসী",
    )),
)

GEOGRAPHY_FLOORS: tuple[tuple[str, str, int, tuple[str, ...]], ...] = (
    ("CORE_DHAKA", "Dhaka industrial core", 700, ("ঢাকা", "গাজীপুর", "নারায়নগঞ্জ", "নারায়ণগঞ্জ", "নরসিংদী", "মুন্সিগঞ্জ")),
    ("CHATTOGRAM", "Chattogram industrial belt", 300, ("চট্টগ্রাম", "কক্সবাজার", "ফেনী", "কুমিল্লা", "ব্রাহ্মণবাড়িয়া")),
    ("NORTHWEST", "Rajshahi & Rangpur divisions", 300, (
        "রাজশাহী", "বগুড়া", "সিরাজগঞ্জ", "পাবনা", "নাটোর", "নওগাঁ", "চাঁপাই নবাবগঞ্জ", "রংপুর", "দিনাজপুর",
        "ঠাকুরগাঁও", "নীলফামারী", "গাইবান্ধা", "কুড়িগ্রাম", "লালমনিরহাট", "পঞ্চগড়",
    )),
    ("SOUTHWEST", "Khulna & Barishal divisions", 250, (
        "খুলনা", "যশোর", "কুষ্টিয়া", "ঝিনাইদহ", "সাতক্ষীরা", "বাগেরহাট", "মাগুরা", "নড়াইল", "চুয়াডাঙ্গা",
        "মেহেরপুর", "বরিশাল", "ভোলা", "পটুয়াখালী", "বরগুনা", "ঝালকাঠি", "পিরোজপুর",
    )),
    ("NORTHEAST", "Sylhet & Mymensingh divisions", 250, (
        "সিলেট", "হবিগঞ্জ", "মৌলভীবাজার", "সুনামগঞ্জ", "ময়মনসিংহ", "জামালপুর", "শেরপুর", "নেত্রকোনা",
    )),
    ("OTHER", "Other / unmatched districts", 200, ()),
)


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def spread_pages(total_records: int | None, desired_rows: int, page_size: int = 30) -> list[int]:
    """Choose deterministic pages spread across a filtered result universe."""
    total = max(0, int(total_records or 0))
    desired = max(0, int(desired_rows))
    if not total or not desired:
        return []
    max_page = max(1, math.ceil(total / page_size))
    requested_pages = min(max_page, max(1, math.ceil(desired / page_size)))
    if requested_pages == 1:
        return [1]

    pages: list[int] = []
    for index in range(requested_pages):
        page = 1 + round(index * (max_page - 1) / (requested_pages - 1))
        if page not in pages:
            pages.append(page)
    return pages


def classify_sector(source_label: str | None) -> str:
    label = _norm(source_label)
    for code, _, _, tokens in SECTOR_TARGETS:
        if any(_norm(token) in label for token in tokens):
            return code
    return "OTHER_MANUFACTURING"


def classify_geography(district: str | None) -> str:
    normalized = _norm(district)
    for code, _, _, districts in GEOGRAPHY_FLOORS:
        if districts and normalized in {_norm(item) for item in districts}:
            return code
    return "OTHER"


@dataclass(frozen=True)
class ValidationCandidate:
    public_id: int
    sector_label: str | None
    district: str | None

    @property
    def sector_family(self) -> str:
        return classify_sector(self.sector_label)

    @property
    def geography_group(self) -> str:
        return classify_geography(self.district)


@dataclass(frozen=True)
class ValidationSelection:
    candidate: ValidationCandidate
    selection_stage: str


def select_validation_sample(candidates: list[ValidationCandidate], target_n: int = 2000) -> list[ValidationSelection]:
    """Select a deterministic validation sample from an already-discovered pool.

    Sector quotas are primary. Geographic floors then fill deficits where possible.
    The function does not imply population representativeness and never invents
    candidates when the discovered pool is smaller than the target.
    """
    ordered = sorted({candidate.public_id: candidate for candidate in candidates}.values(), key=lambda item: item.public_id)
    selected: dict[int, ValidationSelection] = {}

    for code, _, target, _ in SECTOR_TARGETS:
        pool = [c for c in ordered if c.sector_family == code and c.public_id not in selected]
        for candidate in pool[:target]:
            selected[candidate.public_id] = ValidationSelection(candidate, "SECTOR_QUOTA")

    for code, _, target, _ in GEOGRAPHY_FLOORS:
        current = sum(1 for item in selected.values() if item.candidate.geography_group == code)
        need = max(0, target - current)
        pool = [c for c in ordered if c.geography_group == code and c.public_id not in selected]
        for candidate in pool[:need]:
            selected[candidate.public_id] = ValidationSelection(candidate, "GEOGRAPHY_FILL")

    if len(selected) < target_n:
        for candidate in ordered:
            if candidate.public_id not in selected:
                selected[candidate.public_id] = ValidationSelection(candidate, "GENERAL_FILL")
                if len(selected) >= target_n:
                    break

    if len(selected) > target_n:
        stage_order = {"SECTOR_QUOTA": 0, "GEOGRAPHY_FILL": 1, "GENERAL_FILL": 2}
        ranked = sorted(selected.values(), key=lambda item: (stage_order[item.selection_stage], item.candidate.public_id))
        selected = {item.candidate.public_id: item for item in ranked[:target_n]}

    return sorted(selected.values(), key=lambda item: item.candidate.public_id)


def summarize_selection(selection: list[ValidationSelection]) -> dict[str, Counter[str]]:
    return {
        "sector_family": Counter(item.candidate.sector_family for item in selection),
        "geography_group": Counter(item.candidate.geography_group for item in selection),
        "selection_stage": Counter(item.selection_stage for item in selection),
    }
