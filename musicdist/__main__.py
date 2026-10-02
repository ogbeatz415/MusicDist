import argparse
import json
from pathlib import Path
import sys
from .models import Release
from .package import validate_release, build_package


def main():
    p = argparse.ArgumentParser(description='Validate and prepare MusicDist release handoff packages. No DSP uploads.')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['validate', 'package']:
        s = sub.add_parser(name)
        s.add_argument('release', type=Path)
        if name == 'package':
            s.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        release = Release.model_validate_json(args.release.read_text())
        if args.command == 'validate':
            errors, assets = validate_release(release, args.release.parent)
            print(json.dumps({'valid': not errors, 'errors': errors, 'assets_checked': len(assets),
                              'delivery_enabled': False}, indent=2))
            return 1 if errors else 0
        manifest = build_package(release, args.release.parent, args.output)
        print(json.dumps({'package': str(args.output), 'status': manifest['status'], 'delivery_enabled': False}))
        return 0
    except Exception as exc:
        print(f'Cannot prepare release: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
