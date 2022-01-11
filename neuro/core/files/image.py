"""
Transferring image file data into NeuroForest.
"""
import logging

from PIL import (
    Image as PIL_Image,
    ExifTags)
import pyexiv2

from neuro.core.data.str import PathInfo
from neuro.core.deep import File, GeoLocation, Moment
from neuro.utils import time_utils


class Exif(object):
    def __init__(self, img_exif):
        self.raw = img_exif
        self.location = self.get_location()
        self.date_time = self.get_datetime()

    @staticmethod
    def _get_tag_name(tag_id):
        return ExifTags.TAGS[tag_id]

    @staticmethod
    def _convert_to_degrees(value):
        d0 = value[0][0]
        d1 = value[0][1]
        d = float(d0) / float(d1)

        m0 = value[1][0]
        m1 = value[1][1]
        m = float(m0) / float(m1)

        s0 = value[2][0]
        s1 = value[2][1]
        s = float(s0) / float(s1)

        return d + (m / 60.0) + (s / 3600.0)

    @staticmethod
    def _convert_to_meters(rational):
        return rational[0] / rational[1]

    def get_location(self):
        location = GeoLocation()
        try:
            gps_info = self.raw[34853]
            location.longitude = round(self._convert_to_degrees(gps_info[4]), 4)
            location.latitude = round(self._convert_to_degrees(gps_info[2]), 4)
            location.elevation = round(self._convert_to_meters(gps_info[6]), 1)
        except KeyError:
            pass

        return location

    def get_datetime(self):
        try:
            date_time = Moment.from_string(self.raw[36867], time_utils.CODE_PHOTO)
        except KeyError:
            logging.error("Could not get image datetime.")
            return None

        return date_time

    def get_orientation(self):
        return self.raw[274]


class Image(File):
    """Image object."""
    def __init__(self, image_path, **kwargs):
        self.img_exif = dict()
        self.img_info = pyexiv2.Image
        self.img_location = GeoLocation()
        self.img_time = Moment(moment=None)
        super().__init__(image_path, **kwargs)
        self.pil = PIL_Image.open(self.path)

    def __eq__(self, other):
        size = self.size == other.size
        mtime = self.mtime == other.mtime
        name = PathInfo.get_name(self.path) == PathInfo.get_name(other.path)
        location = self.img_location == other.img_location
        return all([size, name, location])

    def fetch_info(self):
        self.img_info = pyexiv2.Image(self.path)

    def get_tid_title(self):
        return "$:/my/img {}".format(str(self.inode))

    def get_first_pixel(self):
        pixel = self.pil.getdata().getpixel((0, 0))
        return pixel

    def get_pixels(self):
        return list(self.pil.getdata())

    def save_pdf(self, pdf_path):
        pdf_buffer = PIL_Image.new("RGB", self.pil.size, (255, 255, 255))
        pdf_buffer.paste(self.pil)

        # Correct rotation.
        self.set_exif()
        orientation = self.img_exif.get_orientation()
        if orientation == 3:
            pdf_buffer = pdf_buffer.rotate(180, expand=True)
        elif orientation == 6:
            pdf_buffer = pdf_buffer.rotate(270, expand=True)
        elif orientation == 8:
            pdf_buffer = pdf_buffer.rotate(90, expand=True)

        pdf_buffer.save(pdf_path, "PDF", resoultion=100.0)

    def set_description(self, description):
        self.fetch_info()
        mods_dict = {"Iptc.Application2.Caption": description}
        self.img_info.modify_iptc(mods_dict)

    def set_exif(self):
        try:
            img_exif = self.pil.getexif()
        except:
            img_exif = None
        if img_exif:
            self.img_exif = Exif(img_exif)

    def set_location(self):
        if self.img_exif:
            self.img_location = self.img_exif.location

    def set_time(self, unix=None):
        if unix:
            moment = Moment(unix, form="unix")
        elif self.img_exif:
            moment = Moment.from_string(self.img_exif.date_time, "%d.%m.%Y %H:%M:%S")
        else:
            moment = Moment(form="now")

        # TODO: data types not correct
        if moment:
            self.img_time = moment
        else:
            self.img_time = self.ctime

    def set(self, **kwargs):
        """Collects the data specific for an image."""
        super().set(**kwargs)
        self.set_exif()
        self.set_location()
        self.set_time()

    def show(self):
        self.pil.show()


class ImageGif(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImageIcns(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImageIcon(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImageJpeg(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImagePng(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImageSvg(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)


class ImageTiff(Image):
    def __init__(self, image_path, **kwargs):
        super().__init__(image_path, **kwargs)
