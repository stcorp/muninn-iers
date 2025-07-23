import os
import re
from datetime import datetime, timedelta
from xml.etree.ElementTree import parse

from muninn.schema import Mapping, Integer
from muninn.struct import Struct

# Date handling routines

romanNumeralMap = (('M', 1000),
                   ('CM', 900),
                   ('D', 500),
                   ('CD', 400),
                   ('C', 100),
                   ('XC', 90),
                   ('L', 50),
                   ('XL', 40),
                   ('X', 10),
                   ('IX', 9),
                   ('V', 5),
                   ('IV', 4),
                   ('I', 1))


def fromRoman(s: str):
    s = s.upper()
    result = 0
    index = 0
    for numeral, integer in romanNumeralMap:
        while s[index:index + len(numeral)] == numeral:
            result += integer
            index += len(numeral)
    return result


def parse_xml_time(xml_time):
    year = int(xml_time.find(f'{NSIERS}dateYear').text)
    month = int(xml_time.find(f'{NSIERS}dateMonth').text)
    day = int(xml_time.find(f'{NSIERS}dateDay').text)
    return datetime(year, month, day)


monthMap = {
    'january': 1,
    'february': 2,
    'march': 3,
    'april': 4,
    'may': 5,
    'june': 6,
    'july': 7,
    'august': 8,
    'september': 9,
    'october': 10,
    'november': 11,
    'december': 12,
    'janvier': 1,
    'fevrier': 2,
    'mars': 3,
    'avril': 4,
    'mai': 5,
    'juin': 6,
    'juillet': 7,
    'aout': 8,
    'septembre': 9,
    'octobre': 10,
    'novembre': 11,
    'decembre': 12,
}


def parse_text_date(text_date, inverted=False):
    if inverted:
        year, month, day = text_date.split()
    else:
        day, month, year = text_date.split()
    return datetime(int(year), monthMap[month.lower()], int(day))


def mjd_to_datetime(mjd):
    # 2000-01-01 equals MJD 51544
    return datetime(2000,1,1) + timedelta(days=mjd-51544)


# Namespaces

class IERSNamespace(Mapping):
    volume = Integer(index=True, optional=True)  # Only applicable for Bulletin A
    number = Integer(index=True)


def namespaces():
    return ["iers"]


def namespace(namespace_name):
    return IERSNamespace


# Product types

NSIERS = "{http://www.iers.org/2003/schema/iers}"


class IERSBulletin(object):

    @property
    def hash_type(self):
        return "md5"

    @property
    def namespaces(self):
        return ["iers"]

    @property
    def use_enclosing_directory(self):
        return False

    def parse_filename(self, filename):
        match = re.match("^" + self.filename_pattern, os.path.basename(filename))
        if match:
            return match.groupdict()
        return None

    def identify(self, paths):
        if len(paths) != 1:
            return False
        for extension in self.extensions:
            pattern = "^" + self.filename_pattern + extension + "$"
            if re.match(pattern, os.path.basename(paths[0])) is not None:
                return True
        return False

    def archive_path(self, properties):
        return self.product_type

    def analyze(self, paths, filename_only=False):
        inpath = paths[0]
        name_attrs = self.parse_filename(inpath)

        properties = Struct()

        core = properties.core = Struct()
        physical_name = os.path.basename(inpath)
        core.product_name, extension = os.path.splitext(physical_name)
        if extension == ".xml":
            core.remote_url = "https://datacenter.iers.org/data/xml/" + physical_name
        elif extension == ".txt":
            core.remote_url = f"https://datacenter.iers.org/data/{self.url_id}/" + physical_name

        iers = properties.iers = Struct()
        iers.number = int(name_attrs['number'])
        if 'volume' in name_attrs:
            iers.volume = fromRoman(name_attrs['volume'])

        if not filename_only:
            if inpath.endswith('.txt'):
                with open(inpath) as file:
                    lines = [line for line in [line.strip() for line in file] if len(line) > 0]
                self._analyze_txt(lines, properties)
            elif inpath.endswith('.xml'):
                self._analyze_xml(parse(inpath).getroot(), properties)

        return properties


class IERSBulletinA(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_A"
        self.filename_pattern = r"bulletina-(?P<volume>[xvi]+)-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]
        self.url_id = 6

    def _analyze_txt(self, lines, properties):
        properties.core.creation_date = parse_text_date(lines[6][:40].strip())
        # start date is the first entry in this section
        idx = lines.index("CELESTIAL POLE OFFSET SERIES:")
        properties.core.validity_start = mjd_to_datetime(int(lines[idx + 4].split()[0]))
        # end date is just before this comment line
        idx = lines.index("These predictions are based on all announced leap seconds.")
        year, month, day = [int(x) for x in lines[idx - 1].split()[:3]]
        properties.core.validity_stop = datetime(year, month, day) + timedelta(days=1)

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}version/{NSIERS}date').text, "%Y-%m-%d")
        times = root.findall(f'{NSIERS}data/{NSIERS}timeSeries/{NSIERS}time')
        properties.core.validity_start = parse_xml_time(times[0])
        properties.core.validity_stop = parse_xml_time(times[-1])
        properties.core.validity_stop += timedelta(days=1)


class IERSBulletinB(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_B"
        self.filename_pattern = r"bulletinb-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]
        self.url_id = 207

    def _analyze_txt(self, lines, properties):
        properties.core.creation_date = parse_text_date(lines[1])
        # start date is the first entry in this section
        idx = lines.index("Final values")
        year, month, day = [int(x) for x in lines[idx + 2].split()[:3]]
        properties.core.validity_start = datetime(year, month, day)
        # end date is the last entry before the next section
        idx = [lines.index(line) for line in lines if "CELESTIAL POLE OFFSETS" in line][0]
        year, month, day = [int(x) for x in lines[idx - 1].split()[:3]]
        properties.core.validity_stop = datetime(year, month, day) + timedelta(days=1)

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}version/{NSIERS}date').text, "%Y-%m-%d")
        times = root.findall(f'{NSIERS}data/{NSIERS}timeSeries/{NSIERS}time')
        properties.core.validity_start = parse_xml_time(times[0])
        properties.core.validity_stop = parse_xml_time(times[-1])
        properties.core.validity_stop += timedelta(days=1)


class IERSBulletinC(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_C"
        self.filename_pattern = r"bulletinc-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]
        self.url_id = 16

    def _analyze_txt(self, lines, properties):
        line = [line for line in lines if "Paris, " in line][0]
        properties.core.creation_date = parse_text_date(line.split(',')[-1].strip())
        line = [line for line in lines if line.startswith('from ')][0]
        properties.core.validity_start = parse_text_date(line.split(',')[0][5:], inverted=True)

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}date').text, "%Y-%m-%d")
        time = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}UT/{NSIERS}startDate').text, "%Y-%m-%d")
        properties.core.validity_start = time


class IERSBulletinD(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_D"
        self.filename_pattern = r"bulletind-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]
        self.url_id = 17

    def _analyze_txt(self, lines, properties):
        match = [line for line in lines if "Paris," in line]
        if len(match) > 0:
            line = match[0]
            properties.core.creation_date = parse_text_date(line.split(',')[-1].strip())
        else:
            line = [line for line in lines if "Paris le " in line][0]
            properties.core.creation_date = parse_text_date(line.split('le')[-1].strip())
        try:
            idx = lines.index("From the")
        except ValueError:
            line = [line for line in lines if line.startswith("From the ")][0]
            properties.core.validity_start = parse_text_date(line[9:].split(',')[0])
        else:
            properties.core.validity_start = parse_text_date(lines[idx+1].split(',')[0])

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}date').text, "%Y-%m-%d")
        time = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}startDate').text, "%Y-%m-%d")
        properties.core.validity_start = time


_product_types = {
    "IERS_A": IERSBulletinA(),
    "IERS_B": IERSBulletinB(),
    "IERS_C": IERSBulletinC(),
    "IERS_D": IERSBulletinD(),
}


def product_types():
    return _product_types.keys()


def product_type_plugin(product_type):
    return _product_types.get(product_type)
