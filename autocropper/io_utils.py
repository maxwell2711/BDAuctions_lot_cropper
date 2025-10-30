# io_utils.py
import os, re, uuid, shutil
from collections import defaultdict

# Accept both "(k)" and "_k" styles
# Examples matched:
#   6.jpg          -> lot=6, idx=None
#   6(1).png       -> lot=6, idx=1
#   6  ( 12 ).JPG  -> lot=6, idx=12
#   6_3.jpeg       -> lot=6, idx=3
_NAME_RE = re.compile(
    r"""^
        (?P<lot>\d+)                      # lot number
        (?:\s*\(\s*(?P<idx_paren>\d+)\s*\) | _(?P<idx_us>\d+) )?
        \.(?P<ext>jpg|jpeg|png)$
    """,
    re.IGNORECASE | re.VERBOSE
)

def parse_name(filename):
    """
    Returns (lot:str, idx:int|None, ext:str) or (None,None,None) if not matched.
    """
    m = _NAME_RE.match(filename)
    if not m: return (None, None, None)
    lot = m.group("lot")
    idx = m.group("idx_paren") or m.group("idx_us")
    idx = int(idx) if idx is not None else None
    ext = m.group("ext")
    return (lot, idx, ext)

def group_images_by_lot(folder):
    """Groups files by lot, supports '(k)' and '_k' schemes."""
    lots = defaultdict(list)
    for fn in os.listdir(folder):
        lot, idx, ext = parse_name(fn)
        if lot is not None:
            lots[lot].append(os.path.join(folder, fn))
    return lots

def numeric_first_sort(keys):
    def keyfn(k):
        try: return (0, int(k))
        except ValueError: return (1, str(k))
    return sorted(keys, key=keyfn)

def _basename_for(lot, idx, ext, scheme):
    if scheme == 'underscore':
        # idx must be >= 1 in underscore scheme
        return f"{lot}_{idx}.{ext}"
    else:
        # parentheses scheme
        return f"{lot}({idx}).{ext}"

def plan_renames_for_lot(paths_for_lot):
    """
    Compute a renaming plan for one lot that enforces your export rules:

    - Parentheses scheme:
        * If files are [6, 6(1), 6(2), ...] → export [6(1), 6(2), 6(3), ...]
          (i.e., base '6' becomes (1), and all existing (k) shift to (k+1)).
        * If files are [6, 6(2), 6(3), ...] → only rename '6'→'6(1)'.
        * If only [6(1), 6(2), ...] → leave as-is.

    - Underscore scheme (6_1, 6_2, ...): leave as-is.

    Returns: list of dicts [{src, dst_basename}], in the desired final order.
    """
    if not paths_for_lot:
        return []

    # Parse and bucket
    by_idx = {}
    lot = None
    ext = None
    base_path = None
    paren_present = False
    underscore_present = False

    for p in paths_for_lot:
        fn = os.path.basename(p)
        lot2, idx, ext2 = parse_name(fn)
        if lot2 is None:  # skip unmatched (shouldn't happen due to grouping)
            continue
        lot = lot or lot2
        ext = ext or ext2

        if idx is None:
            base_path = p  # the "6.jpg" (no index)
        else:
            by_idx[idx] = p
            if '(' in fn: paren_present = True
            if '_' in fn: underscore_present = True

    # If underscore scheme anywhere → leave names as-is
    if underscore_present and not paren_present:
        # produce a stable order by idx ascending
        planned = []
        for k in sorted(by_idx) or []:
            planned.append({"src": by_idx[k], "dst_basename": os.path.basename(by_idx[k])})
        if base_path:
            # There's a base file but using underscore scheme? Rare.
            # Export it as lot_1.ext
            planned = [{"src": base_path, "dst_basename": _basename_for(lot, 1, ext, 'underscore')}] + planned
        return planned

    # Parentheses scheme
    scheme = 'paren'
    has_idx1 = (1 in by_idx)
    # Sort current indexed images
    ordered_idx = sorted(by_idx.keys())

    planned = []

    if base_path and has_idx1:
        # Case: [6, 6(1), 6(2), ...] → shift every (k) to (k+1); base → (1)
        planned.append({"src": base_path, "dst_basename": _basename_for(lot, 1, ext, scheme)})
        for k in ordered_idx:
            planned.append({
                "src": by_idx[k],
                "dst_basename": _basename_for(lot, k + 1, ext, scheme)
            })

    elif base_path and not has_idx1:
        # Case: [6, 6(2), 6(3), ...] → only 6 → 6(1); others unchanged
        planned.append({"src": base_path, "dst_basename": _basename_for(lot, 1, ext, scheme)})
        for k in ordered_idx:
            planned.append({
                "src": by_idx[k],
                "dst_basename": _basename_for(lot, k, ext, scheme)
            })

    else:
        # No base; have [6(1), 6(2)...] or empty → leave as-is
        for k in ordered_idx:
            planned.append({
                "src": by_idx[k],
                "dst_basename": _basename_for(lot, k, ext, scheme)
            })

    return planned

def apply_renames_safely(planned, folder):
    """
    Applies the renaming plan with a two-phase strategy to avoid collisions.
    `planned`: list of {"src": abs_path, "dst_basename": "name.ext"}
    """
    if not planned:
        return 0

    # Phase 1: move all to temporary unique names
    temp_paths = []
    for item in planned:
        src = item["src"]
        tmp = os.path.join(folder, f".tmp_ren_{uuid.uuid4().hex}")
        shutil.move(src, tmp)
        temp_paths.append((tmp, item["dst_basename"]))

    # Phase 2: move to final basenames (resolve conflicts by overwriting)
    count = 0
    for tmp, dst_base in temp_paths:
        final = os.path.join(folder, dst_base)
        # If a file with the same name exists (e.g., duplicates), replace it.
        if os.path.exists(final):
            os.remove(final)
        shutil.move(tmp, final)
        count += 1
    return count

def normalize_output_dir(out_dir):
    """
    Normalizes every lot folder in-place per the export rules.
    Returns total files renamed.
    """
    lots = group_images_by_lot(out_dir)
    total = 0
    for lot, paths in lots.items():
        plan = plan_renames_for_lot(paths)
        total += apply_renames_safely(plan, out_dir)
    return total