import os
import re
import logging
import time
from datetime import datetime, timedelta
from xml.etree.ElementTree import parse

from muninn import Error, Struct
from muninn.schema import Mapping, Integer


logger = logging.getLogger(__name__)


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


def toRoman(n: int):
    result = ""
    for numeral, integer in romanNumeralMap:
        while n >= integer:
            result += numeral
            n -= integer
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
    return datetime(2000, 1, 1) + timedelta(days=mjd-51544)


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

    def remote_url(self, physical_name):
        extension = os.path.splitext(physical_name)[1]
        if extension == ".xml":
            return "https://datacenter.iers.org/data/xml/" + physical_name
        elif extension == ".txt":
            return f"https://datacenter.iers.org/data/{self.url_id}/" + physical_name
        raise Exception("invalid extension")

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
        core.product_name = os.path.splitext(physical_name)[0]
        core.remote_url = self.remote_url(physical_name)

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

    def index_for_physical_name(self, physical_name):
        name_attrs = self.parse_filename(physical_name)
        return int(name_attrs['number'])

    def next_index(self, index):
        return index + 1

    def can_skip_index(self, index):
        return False


class IERSBulletinA(IERSBulletin):
    offset = (18, 1)
    missing = [(18, 5)]

    def __init__(self):
        self.product_type = "IERS_A"
        self.filename_pattern = r"bulletina-(?P<volume>[xvi]+)-(?P<number>[\d]{3})"
        self.extensions = [".txt", ".xml"]
        self.url_id = 6

    def _analyze_txt(self, lines, properties):
        idx = 0
        while lines[idx].startswith('*'):
            idx += 1
        properties.core.creation_date = parse_text_date(lines[idx][:40].strip())
        # start date is the first entry in this section
        try:
            idx = lines.index("CELESTIAL POLE OFFSET SERIES:")
        except ValueError:
            # if celestial pole offset series does not exist then use the first date from this section
            idx = lines.index("COMBINED EARTH ORIENTATION PARAMETERS:")
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

    def index_for_physical_name(self, physical_name):
        name_attrs = self.parse_filename(physical_name)
        return (fromRoman(name_attrs['volume']), int(name_attrs['number']))

    def physical_name_for_index(self, format, index):
        return "-".join(["bulletina", toRoman(index[0]).lower(), f"{index[1]:03}"]) + "." + format

    def next_index(self, index):
        if index[1] == 53:
            return (index[0] + 1, 1)
        else:
            return (index[0], index[1] + 1)

    def can_skip_index(self, index):
        if index in self.missing:
            return True
        if index[1] == 53:
            return True


class IERSBulletinB(IERSBulletin):
    offset = 253

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

    def physical_name_for_index(self, format, index):
        return "-".join(["bulletinb", f"{index:03}"]) + "." + format


class IERSBulletinC(IERSBulletin):
    offset = 10

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

    def physical_name_for_index(self, format, index):
        return "-".join(["bulletinc", f"{index:03}"]) + "." + format


class IERSBulletinD(IERSBulletin):
    offset = 21
    missing = [25, 26, 27, 29, 34, 35, 38, 42, 45, 47, 48, 49]

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

    def physical_name_for_index(self, format, index):
        return "-".join(["bulletind", f"{index:03}"]) + "." + format

    def can_skip_index(self, index):
        return index in self.missing


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


# Synchronizer

class IERSSynchronizer(object):

    def __init__(self, config):
        '''
        configuration can contain:
        - format (string): mandatory; either 'xml' or 'txt'
        - rate_limit (int): optional; maximum number of requests per minute; default is 120;
          introduces a delay between each subsequent request; when set to 0, no delay will be used
        '''
        if 'format' not in config:
            raise Error("missing \"format\" setting in configuration for IERS synchronizer")
        self.format = config['format']
        self.rate_limit = config.get("rate_limit", 120)
        if self.format not in ['xml', 'txt']:
            raise Error(f"invalid IERS synchronizer \"format\" setting; \"{self.format}\" not one of: xml, txt")

    def sync(self, archive, product_types=None, start=None, end=None, force=False):
        import requests

        if product_types is not None:
            for product_type in product_types:
                if product_type not in _product_types:
                    raise Error(f"product_type \"{product_type}\" is not one of: {', '.join(_product_types.keys())}")
        else:
            product_types = _product_types.keys()

        if start is not None:
            raise Error("\"start\" parameter not supported")
        if end is not None:
            raise Error("\"end\" parameter not supported")
        if force:
            raise Error("\"force\" parameter not supported")

        for product_type in product_types:
            plugin = _product_types[product_type]

            # find latest in archive
            result = archive.search(where="product_type==@product_type", parameters={'product_type': product_type},
                                    property_names=["physical_name"], order_by=["-iers.volume", "-iers.number"],
                                    limit=1)
            if len(result) > 0:
                index = plugin.next_index(plugin.index_for_physical_name(result[0].core.physical_name))
            else:
                index = plugin.offset

            while True:
                physical_name = plugin.physical_name_for_index(self.format, index)
                resp = requests.head(plugin.remote_url(physical_name))
                if resp.status_code == 200:
                    logger.info(f"adding '{physical_name}'")
                    properties = plugin.analyze([physical_name], filename_only=True)
                    properties.core.uuid = archive.generate_uuid()
                    properties.core.active = True
                    properties.core.size = int(resp.headers["Content-Length"])
                    properties.core.product_type = product_type
                    properties.core.physical_name = physical_name
                    archive.create_properties(properties)
                elif resp.status_code == 404:
                    if not plugin.can_skip_index(index):
                        break
                else:
                    resp.raise_for_status()
                index = plugin.next_index(index)
                if self.rate_limit is not None and self.rate_limit > 0:
                    time.sleep(1 / (self.rate_limit / 60))


def synchronizer(config):
    return IERSSynchronizer(config)
