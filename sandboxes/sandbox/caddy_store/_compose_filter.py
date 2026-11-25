"""Stdlib-only docker-compose.override.yml external network filter for fresh-VPS restore."""

from __future__ import annotations

DEFAULT_CADDY_NETWORK = "dbhost-network"


def _split_top_level_yaml_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Splits YAML lines into [(top_key, section_lines)] preserving order."""
    sections: list[tuple[str, list[str]]] = []
    cur_key = ""
    cur_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if line and not line[0].isspace() and not stripped.startswith("#") and ":" in line:
            if cur_lines:
                sections.append((cur_key, cur_lines))
            cur_key = line.split(":", 1)[0].strip()
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_lines:
        sections.append((cur_key, cur_lines))
    return sections


def _parse_external_network_aliases(
    net_section: list[str],
    existing_networks: set[str],
    required_networks: set[str],
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    """Inspects top-level networks section and returns (kept_blocks_map, missing_aliases, missing_actuals)."""
    allowed = existing_networks | required_networks
    children: list[tuple[str, list[str]]] = []
    cur_alias = ""
    cur_block: list[str] = []
    base_indent: int | None = None

    for line in net_section[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if cur_block:
                cur_block.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is None or indent <= base_indent:
            if ":" in stripped and not stripped.startswith("-"):
                if cur_block:
                    children.append((cur_alias, cur_block))
                base_indent = indent
                cur_alias = stripped.split(":", 1)[0].strip().strip("\"'")
                cur_block = [line]
                continue
        if cur_block:
            cur_block.append(line)
    if cur_block:
        children.append((cur_alias, cur_block))

    kept_lines: dict[str, list[str]] = {}
    missing_aliases: list[str] = []
    missing_actuals: list[str] = []
    for alias, block in children:
        is_ext = False
        actual_name = alias
        for b_line in block[1:]:
            b_clean = b_line.split("#", 1)[0].strip()
            if b_clean.startswith("external:"):
                val = b_clean.split(":", 1)[1].strip().lower()
                is_ext = val in ("true", "yes", "1")
            elif b_clean.startswith("name:"):
                val = b_clean.split(":", 1)[1].strip().strip("\"'")
                if val:
                    actual_name = val
        if is_ext and actual_name not in allowed:
            missing_aliases.append(alias)
            missing_actuals.append(actual_name)
        else:
            kept_lines[alias] = block

    return kept_lines, missing_aliases, missing_actuals


def _consume_networks_block(
    svc_lines: list[str],
    start_idx: int,
    missing_aliases: set[str],
) -> tuple[list[str], int]:
    """Filters one `networks:` block inside a service definition."""
    header = svc_lines[start_idx]
    net_indent = len(header) - len(header.lstrip(" "))
    block_items: list[str] = []
    j = start_idx + 1
    while j < len(svc_lines):
        cand = svc_lines[j]
        c_strip = cand.strip()
        if not c_strip or c_strip.startswith("#"):
            j += 1
            continue
        c_indent = len(cand) - len(cand.lstrip(" "))
        if c_indent <= net_indent:
            break
        if c_strip.startswith("-"):
            item_name = c_strip[1:].strip().strip("\"'")
            if item_name not in missing_aliases:
                block_items.append(cand)
            j += 1
        elif ":" in c_strip:
            map_key = c_strip.split(":", 1)[0].strip().strip("\"'")
            sub_start = j
            j += 1
            while j < len(svc_lines):
                sc = svc_lines[j]
                sc_strip = sc.strip()
                if sc_strip and not sc_strip.startswith("#") and (len(sc) - len(sc.lstrip(" "))) <= c_indent:
                    break
                j += 1
            if map_key not in missing_aliases:
                block_items.extend(svc_lines[sub_start:j])
        else:
            block_items.append(cand)
            j += 1
    return ([header, *block_items] if block_items else []), j


def _filter_services_section(svc_lines: list[str], missing_aliases: set[str]) -> list[str]:
    """Removes missing network references from services.*.networks entries."""
    out: list[str] = []
    idx = 0
    while idx < len(svc_lines):
        line = svc_lines[idx]
        if line.split("#", 1)[0].strip() == "networks:":
            filtered_block, idx = _consume_networks_block(svc_lines, idx, missing_aliases)
            out.extend(filtered_block)
            continue
        out.append(line)
        idx += 1

    svc_indent: int | None = None
    for ln in out[1:]:
        s = ln.strip()
        if s and not s.startswith("#"):
            svc_indent = len(ln) - len(ln.lstrip(" "))
            break

    pruned: list[str] = []
    s_idx = 0
    while s_idx < len(out):
        line = out[s_idx]
        stripped = line.split("#", 1)[0].strip()
        indent = len(line) - len(line.lstrip(" "))
        if svc_indent is not None and s_idx > 0 and indent == svc_indent and stripped.endswith(":"):
            has_child = False
            for k in range(s_idx + 1, len(out)):
                c = out[k].strip()
                if not c or c.startswith("#"):
                    continue
                if (len(out[k]) - len(out[k].lstrip(" "))) > indent:
                    has_child = True
                break
            if not has_child:
                s_idx += 1
                continue
        pruned.append(line)
        s_idx += 1

    has_services_body = any(ln.strip() and not ln.strip().startswith("#") for ln in pruned[1:])
    return pruned if has_services_body else []


def filter_compose_override_networks(
    raw_yaml: str,
    existing_networks: set[str],
    required_networks: set[str] | None = None,
) -> tuple[str | None, list[str]]:
    """Filters external networks in docker-compose.override.yml to those existing on the host."""
    req = required_networks if required_networks is not None else {DEFAULT_CADDY_NETWORK}
    sections = _split_top_level_yaml_sections(raw_yaml.splitlines())

    missing_aliases: list[str] = []
    missing_actuals: list[str] = []
    kept_net_blocks: dict[str, list[str]] = {}
    for key, sec_lines in sections:
        if key == "networks":
            kept_net_blocks, missing_aliases, missing_actuals = _parse_external_network_aliases(
                sec_lines, existing_networks, req
            )
            break

    if not missing_aliases:
        return raw_yaml, []

    missing_set = set(missing_aliases)
    new_sections: list[str] = []
    for key, sec_lines in sections:
        if key == "networks":
            if kept_net_blocks:
                new_sections.append(sec_lines[0])
                for blk in kept_net_blocks.values():
                    new_sections.extend(blk)
        elif key == "services":
            filtered_svc = _filter_services_section(sec_lines, missing_set)
            if filtered_svc:
                new_sections.extend(filtered_svc)
        else:
            new_sections.extend(sec_lines)

    meaningful = [ln for ln in new_sections if ln.strip() and not ln.strip().startswith("#")]
    if not meaningful:
        return None, sorted(set(missing_actuals))
    return "\n".join(new_sections).rstrip() + "\n", sorted(set(missing_actuals))
