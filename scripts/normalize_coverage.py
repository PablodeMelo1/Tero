"""Make reports portable between test runners and SonarCloud's checkout."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('ui', 'admin', 'checkout', 'catalog', 'orders', 'cart', 'ci')


def source_path(value, prefix):
    """Return a portable project-relative path without duplicating its prefix."""
    path = Path(value)
    if path.is_absolute():
        path = path.relative_to(ROOT)
    elif path.parts[:len(prefix.parts)] != prefix.parts:
        path = prefix / path
    if '..' in path.parts:
        raise ValueError('Coverage path must stay inside the project')
    return path.as_posix()


def normalize(service):
    if service not in SERVICES:
        raise ValueError('Unknown service')
    root = Path('src') / service
    if service in ('ui', 'admin', 'checkout'):
        report = root / 'coverage/lcov.info'
        # File content is only the write_text payload, never its destination.
        # The destination above depends only on the validated service.
        report.write_text(''.join(
            'SF:' + source_path(line[3:].strip(), root) + '\n' if line.startswith('SF:') else line
            for line in report.read_text().splitlines(keepends=True)
        ))
    elif service in ('catalog', 'orders'):
        report = root / 'coverage.out'
        report.write_text(report.read_text().replace(f'retail-store/{service}/', str(root) + '/'))
    elif service in ('cart', 'ci'):
        report = root / 'coverage/coverage.xml' if service == 'cart' else Path('coverage/ci-coverage.xml')
        prefix = root / 'app' if service == 'cart' else Path('scripts')
        tree = ET.parse(report)
        for source in tree.findall('./sources/source'):
            source.text = '.'
        for cls in tree.findall('.//class'):
            filename = cls.attrib['filename']
            # pytest-cov may emit app/foo.py when multiple source roots exist.
            if service == 'cart' and filename.startswith('app/'):
                filename = str(root / filename)
            cls.set('filename', source_path(filename, prefix))
        tree.write(report, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    normalize(sys.argv[1])
