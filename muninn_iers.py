import os
import re
from datetime import datetime, timedelta
from xml.etree.ElementTree import parse

from muninn.schema import Mapping, Integer
from muninn.struct import Struct

# Roman numeral handling

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


def parse_xml_time(xml_time):
    year = int(xml_time.find(f'{NSIERS}dateYear').text)
    month = int(xml_time.find(f'{NSIERS}dateMonth').text)
    day = int(xml_time.find(f'{NSIERS}dateDay').text)
    return datetime(year, month, day)


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
        core.product_name = os.path.splitext(os.path.basename(inpath))[0]

        iers = properties.iers = Struct()
        iers.number = int(name_attrs['number'])
        if 'volume' in name_attrs:
            iers.volume = fromRoman(name_attrs['volume'])

        if not filename_only:
            if inpath.endswith('.xml'):
                self._analyze_xml(parse(inpath).getroot(), properties)

        return properties


class IERSBulletinA(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_A"
        self.filename_pattern = r"bulletina-(?P<volume>[xvi]+)-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]

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

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}date').text, "%Y-%m-%d")
        time = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}UT/{NSIERS}startDate').text, "%Y-%m-%d")
        properties.core.validity_start = time
        properties.core.validity_stop = time


class IERSBulletinD(IERSBulletin):

    def __init__(self):
        self.product_type = "IERS_D"
        self.filename_pattern = r"bulletind-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]

    def _analyze_xml(self, root, properties):
        properties.core.creation_date = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}date').text, "%Y-%m-%d")
        time = datetime.strptime(root.find(f'{NSIERS}data/{NSIERS}startDate').text, "%Y-%m-%d")
        properties.core.validity_start = time
        properties.core.validity_stop = time


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
