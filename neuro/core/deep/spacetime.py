import datetime
import time
import logging

from neuro.core import NeuroObject


class Location(NeuroObject):
    def __init__(self, longitude=float(), latitude=float(), elevation=float()):
        self.longitude = longitude
        self.latitude = latitude
        self.elevation = elevation

    def __bool__(self):
        return bool(self.longitude and self.latitude)

    def __eq__(self, other):
        lat = self.latitude == other.latitude
        lon = self.longitude == other.longitude
        ele = self.elevation == other.elevation
        return all([lat, lon, ele])

    @staticmethod
    def to_dms(decimal):
        """
        DMS = degrees minutes seconds
        :param decimal: decimal degrees
        :return: DMS
        """
        mnt, sec = divmod(decimal * 3600, 60)
        deg, mnt = divmod(mnt, 60)
        return str(int(deg)) + "°" + str(int(mnt)) + "'" + str(sec) + "\""

    def from_gps_dict(self, gps_dict, key_lon="lon", key_lat="lat", key_ele="ele"):
        self.longitude = gps_dict[key_lon]
        self.latitude = gps_dict[key_lat]
        self.elevation = gps_dict[key_ele]


class Moment(NeuroObject):
    def __init__(self, moment=None, form="unix"):
        """
        Initialized the Moment object and determines unix time.
        :param moment: date and time input
        :param form: form of moment input
        """
        if not moment:
            moment = time.time()

        if form == "unix":
            self.unix = moment
        elif form == "utc":
            if len(moment) == 24 and moment[-1] == "Z":
                moment.replace("Z", "+0000")
            self.unix = datetime.datetime.strptime(moment, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
        elif form == "now":
            self.unix = time.time()
        elif form == "tw5":
            self.unix = datetime.datetime.strptime(moment + "+0000", "%Y%m%d%H%M%S%f%z").timestamp()
        else:
            logging.error("Form not recognized.")

    def __bool__(self):
        return bool(self.unix)

    def __eq__(self, other):
        return self.unix == other.unix

    def __gt__(self, other):
        return self.unix > other.unix

    def __lt__(self, other):
        return self.unix < other.unix

    def __repr__(self):
        return datetime.datetime.fromtimestamp(self.unix).strftime("%Y-%m-%d %H:%M:%S")

    def __sub__(self, other):
        if isinstance(other, Moment):
            return self.unix - other.unix
        else:
            return NotImplemented

    @classmethod
    def from_string(cls, datetime_string, datetime_format):
        """
        Import from UTC string.

        :param datetime_string:
        :param datetime_format: refer to https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
        :return:
        """
        try:
            dt = datetime.datetime.strptime(datetime_string, datetime_format)
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            unix = dt.timestamp()
        except ValueError:
            logging.error(f"Time data {datetime_string} does not match format {datetime_format}")
            return cls()

        return cls(unix)

    @classmethod
    def from_tid_val(cls, tid_val):
        return cls.from_string(tid_val, "%Y%m%d%H%M%S%f")

    @classmethod
    def from_iso(cls, iso_string):
        return cls.from_string(iso_string, "%Y-%m-%dT%H:%M:%S.%f%z")

    def to_format(self, time_format):
        dt = datetime.datetime.fromtimestamp(self.unix, tz=datetime.UTC)
        return dt.strftime(time_format)

    def to_prog(self):
        return self.to_format("%Y%m%d%H%M%S")

    def to_slv(self):
        return self.to_format("%d.%m.%Y %H:%M:%S")

    def to_tid_val(self):
        return self.to_format("%Y%m%d%H%M%S%f")

    def to_tid_date(self):
        tid_date = self.to_format("%Y-%m-%d")
        if tid_date[0] == "0":
            tid_date = tid_date[1:]
        return tid_date

    def to_iso(self):
        return self.to_format("%Y-%m-%dT%H:%M:%S.%f")

    def to_iso_z(self):
        return self.to_format("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
