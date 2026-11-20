"""Make reports portable between test runners and SonarCloud's checkout."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def normalize(service):
    root = Path('src') / service
    if service in ('ui', 'admin', 'checkout'):
        report = root / 'coverage/lcov.info'
        report.write_text(''.join(
            'SF:' + str(root / line[3:].strip()) + '\n' if line.startswith('SF:') else line
            for line in report.read_text().splitlines(keepends=True)
        ))
    elif service in ('catalog', 'orders'):
        report = root / 'coverage.out'
        report.write_text(report.read_text().replace(f'retail-store/{service}/', str(root) + '/'))
    elif service == 'cart':
        report = root / 'coverage/coverage.xml'
        tree = ET.parse(report)
        for source in tree.findall('./sources/source'):
            source.text = '.'
        for cls in tree.findall('.//class'):
            cls.set('filename', str(root / 'app' / cls.attrib['filename']))
        tree.write(report, encoding='utf-8', xml_declaration=True)
    else:
        raise ValueError('Unknown service')


if __name__ == '__main__':
    normalize(sys.argv[1])
