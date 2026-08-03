"""Simple inventory management CLI for a small workshop.

Stores items in a JSON file and supports adding stock, removing stock,
searching, and printing a restock report for items below their minimum level.
"""

import argparse
import json
import os
import sys
from datetime import datetime

INVENTORY_FILE = "inventory.json"


def load_inventory(path):
    """Load inventory from disk, returning an empty dict if missing."""
    if not os.path.exists(path):
        return {}
    with open(path, "r") as handle:
        return json.load(handle)


def save_inventory(inventory, path):
    """Write inventory back to disk with a timestamp."""
    inventory["_last_saved"] = datetime.now().isoformat()
    with open(path, "w") as handle:
        json.dump(inventory, handle, indent=2, sort_keys=True)


def add_item(inventory, name, quantity, minimum):
    """Add stock for an item, creating it if it does not exist yet."""
    record = inventory.get(name, {"quantity": 0, "minimum": minimum})
    record["quantity"] += quantity
    record["minimum"] = minimum
    inventory[name] = record
    print(f"Added {quantity} x {name} (now {record['quantity']})")


def remove_item(inventory, name, quantity):
    """Remove stock for an item, refusing to go below zero."""
    if name not in inventory:
        print(f"Unknown item: {name}", file=sys.stderr)
        return False
    record = inventory[name]
    if record["quantity"] < quantity:
        print(f"Only {record['quantity']} x {name} in stock", file=sys.stderr)
        return False
    record["quantity"] -= quantity
    print(f"Removed {quantity} x {name} (now {record['quantity']})")
    return True


def search_items(inventory, term):
    """Return item names containing the search term, case-insensitive."""
    term = term.lower()
    matches = []
    for name in sorted(inventory):
        if name.startswith("_"):
            continue
        if term in name.lower():
            matches.append(name)
    return matches


def restock_report(inventory):
    """Print every item whose quantity is at or below its minimum."""
    print("Restock report:")
    low = 0
    for name, record in sorted(inventory.items()):
        if name.startswith("_"):
            continue
        if record["quantity"] <= record["minimum"]:
            shortfall = record["minimum"] - record["quantity"]
            print(f"  {name}: {record['quantity']} on hand, order {shortfall + 5}")
            low += 1
    if low == 0:
        print("  All items sufficiently stocked.")


def build_parser():
    parser = argparse.ArgumentParser(description="Workshop inventory tool")
    sub = parser.add_subparsers(dest="command", required=True)

    add_cmd = sub.add_parser("add", help="Add stock")
    add_cmd.add_argument("name")
    add_cmd.add_argument("quantity", type=int)
    add_cmd.add_argument("--minimum", type=int, default=3)

    remove_cmd = sub.add_parser("remove", help="Remove stock")
    remove_cmd.add_argument("name")
    remove_cmd.add_argument("quantity", type=int)

    search_cmd = sub.add_parser("search", help="Search items")
    search_cmd.add_argument("term")

    sub.add_parser("report", help="Show restock report")
    return parser


def main():
    args = build_parser().parse_args()
    inventory = load_inventory(INVENTORY_FILE)

    if args.command == "add":
        add_item(inventory, args.name, args.quantity, args.minimum)
    elif args.command == "remove":
        remove_item(inventory, args.name, args.quantity)
    elif args.command == "search":
        for name in search_items(inventory, args.term):
            print(name)
    elif args.command == "report":
        restock_report(inventory)

    save_inventory(inventory, INVENTORY_FILE)


if __name__ == "__main__":
    main()