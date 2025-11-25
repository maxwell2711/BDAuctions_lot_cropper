import csv
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Iterable, Set

# -------------------------------
# Filename parsing & schemes
# -------------------------------
# Lots like: 6, 6a, 101B, etc.
# Schemes supported:
#   <lot>.ext                   (idx=0, "bare")
#   <lot> (<n>).ext             (idx=n, "paren")
#   <lot>_<n>.ext               (idx=n, "under")
#   <lot>-<n>.ext               (idx=n, "hyphen")

_LOT = r"(?P<lot>\d+[A-Za-z]*)"
_EXT = r"(?P<ext>jpe?g|png)"
_IDX = r"(?P<idx>\d+)"

_PAREN_IDX = re.compile(rf"^{_LOT}\s*\(({_IDX})\)\.({_EXT})$", re.IGNORECASE)
_UNDER_IDX = re.compile(rf"^{_LOT}\s*_{_IDX}\.({_EXT})$", re.IGNORECASE)
_HYPH_IDX  = re.compile(rf"^{_LOT}\s*-{_IDX}\.({_EXT})$", re.IGNORECASE)
_BARE      = re.compile(rf"^{_LOT}\.({_EXT})$", re.IGNORECASE)

def parse_image_name(path_or_name: str) -> Optional[Tuple[str, int, str, str]]:
    """
    Return (lot, idx, scheme, ext) or None if not a supported image.
    idx=0 for bare; 1.. for indexed.
    scheme in {"bare","paren","under","hyphen"}.
    ext includes extension without dot, lowercase (e.g., 'jpg').
    """
    name = os.path.basename(path_or_name)

    m = _PAREN_IDX.match(name)
    if m:
        return m.group("lot"), int(m.group("idx")), "paren", m.group(3).lower()

    m = _UNDER_IDX.match(name)
    if m:
        return m.group("lot"), int(m.group("idx")), "under", m.group(3).lower()

    m = _HYPH_IDX.match(name)
    if m:
        return m.group("lot"), int(m.group("idx")), "hyphen", m.group(3).lower()

    m = _BARE.match(name)
    if m:
        return m.group("lot"), 0, "bare", m.group(2).lower()

    return None

def display_order_for_path(path_or_name: str) -> Optional[int]:
    """
    1-based display order: bare and 1 -> 1, 2 -> 2, etc.
    Returns None if not a supported image.
    """
    parsed = parse_image_name(path_or_name)
    if not parsed:
        return None
    _lot, idx, _scheme, _ext = parsed
    return 1 if idx == 0 else idx

def sort_paths_by_index(paths: Iterable[str]) -> List[str]:
    """
    Sort for a single lot: bare(idx=0) first, then 1,2,3...
    Non-matching filenames go to the end.
    """
    def key(p: str):
        parsed = parse_image_name(p)
        if parsed:
            lot, idx, scheme, _ext = parsed
            return (0, idx)
        return (1, 10**9, os.path.basename(p).lower())
    return sorted(paths, key=key)

# -------------------------------
# Grouping & lot sorting
# -------------------------------

def group_images_by_lot(folder: str) -> Dict[str, List[str]]:
    """
    Returns { lot_id(str): [sorted image paths...] } for all images in a folder.
    Distinguishes '6' vs '6a' vs '6b', etc.
    """
    lot_dict: Dict[str, List[str]] = defaultdict(list)
    try:
        for fname in os.listdir(folder):
            parsed = parse_image_name(fname)
            if not parsed:
                continue
            lot, _idx, _scheme, _ext = parsed
            lot_dict[lot].append(os.path.join(folder, fname))
    except FileNotFoundError:
        pass

    for lot, arr in lot_dict.items():
        lot_dict[lot] = sort_paths_by_index(arr)
    return lot_dict

_LOT_SPLIT = re.compile(r"^(\d+)([A-Za-z]*)$")

def _lot_sort_key(lot: str):
    """
    Sort lots by (number, suffix), then others lexicographically.
    E.g. 5 < 5a < 6 < 6a < 10 < 10a < B1 < C
    """
    m = _LOT_SPLIT.match(lot)
    if m:
        n = int(m.group(1))
        sfx = m.group(2).lower()
        return (0, n, sfx)
    return (1, lot.lower())

def numeric_first_sort(keys: Iterable[str]) -> List[str]:
    return sorted(keys, key=_lot_sort_key)

# -------------------------------
# Export rename policy
# -------------------------------

def _target_name(lot: str, idx: int, scheme: str, ext: str) -> str:
    if scheme == "paren":
        return f"{lot} ({idx}).{ext}"
    if scheme == "under":
        return f"{lot}_{idx}.{ext}"
    if scheme == "hyphen":
        return f"{lot}-{idx}.{ext}"
    raise ValueError("scheme must be paren/under/hyphen")

def _detect_index_scheme(paths: List[str]) -> Optional[str]:
    """Detect which indexed scheme is in use among given paths."""
    seen = set()
    for p in paths:
        parsed = parse_image_name(p)
        if not parsed:
            continue
        _lot, idx, scheme, _ext = parsed
        if idx > 0:
            seen.add(scheme)
    if "paren" in seen:  return "paren"
    if "under" in seen:  return "under"
    if "hyphen" in seen: return "hyphen"
    return None  # no indexed files present

def compute_export_renames_for_lot(paths: List[str]) -> Dict[str, str]:
    """
    Given absolute file paths for ONE lot, compute a plan {src_abs: dst_abs}
    that enforces:
      - If bare exists and index 1 exists => shift all indexed n -> n+1, then bare -> 1
      - If bare exists and index 1 missing => bare -> 1
      - If only indexed and index 1 missing => promote smallest index to 1
    Works for paren/under/hyphen. If mixed, prefers paren, else under, else hyphen.
    """
    paths = [p for p in paths if parse_image_name(p)]
    if not paths:
        return {}

    # All belong to same lot by contract; read lot/ext from any
    # But ext can differ; we preserve each file's ext individually.
    # Scheme detection:
    scheme = _detect_index_scheme(paths) or "paren"

    # Partition by idx
    by_idx: Dict[int, List[str]] = defaultdict(list)
    bare = []
    lot_name = None
    for p in paths:
        lot, idx, _scheme, ext = parse_image_name(p)  # type: ignore
        lot_name = lot if lot_name is None else lot_name
        if idx == 0:
            bare.append(p)
        else:
            by_idx[idx].append(p)

    plan: Dict[str, str] = {}

    # If more than one bare, keep the lexicographically first as the "bare source"
    # and treat others as normal files (rare edge case).
    bare_src = bare[0] if bare else None

    # Case A: bare exists
    if bare_src:
        # If index 1 currently occupied, shift indexes upward (descending to avoid collisions)
        if 1 in by_idx:
            # Determine max index present
            max_idx = max(by_idx.keys()) if by_idx else 1
            for n in range(max_idx, 0, -1):
                if n in by_idx:
                    for p in by_idx[n]:
                        lot, _i, _s, ext = parse_image_name(p)  # type: ignore
                        dst_name = _target_name(lot, n + 1, scheme, ext)
                        plan[p] = os.path.join(os.path.dirname(p), dst_name)

        # Finally map bare -> 1
        lot, _i, _s, ext = parse_image_name(bare_src)  # type: ignore
        dst_name = _target_name(lot, 1, scheme, ext)
        plan[bare_src] = os.path.join(os.path.dirname(bare_src), dst_name)
        return plan

    # Case B: only indexed; ensure index 1 exists
    if 1 not in by_idx and by_idx:
        smallest = min(by_idx.keys())
        # Promote the *first* file at smallest index to index 1
        p0 = by_idx[smallest][0]
        lot, _i, _s, ext = parse_image_name(p0)  # type: ignore
        dst_name = _target_name(lot, 1, scheme, ext)
        plan[p0] = os.path.join(os.path.dirname(p0), dst_name)

    return plan

def _apply_renames(plan: Dict[str, str]) -> None:
    """
    Safely apply {src_abs: dst_abs} with cycle breaking via temp names.
    """
    if not plan:
        return

    folder = None
    temps = {}
    used = set()

    # Collect folder & used names
    for src, dst in plan.items():
        folder = folder or os.path.dirname(src)
        used.add(os.path.basename(src))
        used.add(os.path.basename(dst))

    def _temp_for(dst_path: str) -> str:
        base = os.path.basename(dst_path)
        stem, ext = os.path.splitext(base)
        k = 0
        while True:
            tmp = f"{stem}.__tmp__{k}{ext}"
            if tmp not in used:
                used.add(tmp)
                return os.path.join(folder, tmp)  # type: ignore
            k += 1

    # Phase 1: move to temps
    for src, dst in plan.items():
        if os.path.exists(src):
            tmp = _temp_for(dst)
            os.replace(src, tmp)
            temps[tmp] = dst

    # Phase 2: temps -> final
    for tmp, dst in temps.items():
        os.replace(tmp, dst)

def normalize_output_dir(out_dir: str) -> int:
    """
    For every lot in out_dir, enforce the export filename policy on disk.
    Returns number of files renamed.
    """
    count = 0
    groups = group_images_by_lot(out_dir)
    for _lot, files in groups.items():
        plan = compute_export_renames_for_lot(files)
        if plan:
            _apply_renames(plan)
            count += len(plan)
    return count


def compute_already_cropped_lots(input_dir: str, output_dir: str) -> Set[str]:
    """
    Compare input and output directories to find lots that are already complete.
    
    Logic:
      - For each lot that appears in both input_dir and output_dir:
          input_count = number of image files for that lot in input_dir
          output_count = number of image files for that lot in output_dir
        
        If output_count >= input_count:
            -> that lot is already done (all originals have been cropped)
        Else:
            -> that lot is NOT done (new images were added or still processing)
    
    Returns a set of lot IDs that can be skipped.
    """
    input_groups = group_images_by_lot(input_dir)
    output_groups = group_images_by_lot(output_dir)
    
    done: Set[str] = set()
    
    for lot, input_files in input_groups.items():
        input_count = len(input_files)
        output_count = len(output_groups.get(lot, []))
        
        # If output has as many or more files than input, lot is done
        if output_count >= input_count:
            done.add(lot)
    
    return done