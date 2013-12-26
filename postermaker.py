#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2013 Adrien Vergé

__author__ = "Adrien Vergé"
__copyright__ = "Copyright 2013, Adrien Vergé"
__license__ = "GPL"
__version__ = "1.0"

"""
The design is based on LightBox, as presented in [1].

[1]: http://blog.vjeux.com/2012/image/image-layout-algorithm-lightbox.html

-------------------------
|                       |
|                       |
|        Page           |  The "Page" object represents the whole page that
|                       |  will give the final assembled image.
|                       |
-------------------------

-------------------------
|       |       |       |
|       |Column |       |
|       |       |Column |  A page is divided into columns.
|Column |       |       |
|       |       |       |
-------------------------

-------------------------
| Photo | Photo     x<--|-------- PhotoExtent
|-------|               |
| Photo |---------------|  Each column contains photos. When a photo is located
|-------| Photo |       |  in several columns, its "extended" flag is set, and
| Photo |       | Photo |  a "PhotoExtent" object is added to the column on the
-------------------------  right.

The layout placing process can be divided in three phases.

Phase A: Fill columns with photos.
	Photos are added to columns, one by one, until they are no more photos.
	Each new photo is put in the smallest column, so as to have balanced
	columns.  If two columns have approximately the same height, a photo can be
	"extended" to fit two columns. In this case, the "Photo" object is put in
	the first column, and the second column takes a "PhotoExtent" object to
	save the taken space.

Phase B: Set all columns to same height.
	A global common height is computed for all columns, and every of them is
	stressed or extended to this common length.  This can result in a decrease
	or increase in columns' width.

Phase C: Adapt columns' width.
	Since every column images may have different widths, each column new width
	is set to the smallest width amongst its images.

This process makes images with holes and cropped images, whose importance can
be measured with the "wasted_space" and "hidden_space" functions.  A simple way
to get a good layout is to generate many and keep the one with the smallest of
these values.

"""

import copy
import math
import PIL.Image
import PIL.ImageDraw
import PIL.ImageTk
import random
import tkinter as tk
from tkinter import filedialog

def random_color():
	r = random.randrange(256)
	g = random.randrange(256)
	b = random.randrange(256)
	return (r, g, b)

class Photo:

	def __init__(self, imagefile, w, h, x=0, y=0):
		self.imagefile = imagefile

		self.real_w = self.w = w
		self.real_h = self.h = h

		self.x = x
		self.y = y

		self.extended = False
		self.spacings = []

		self.orientation = 0

	# ---------------------
	#  Rendering functions
	# ---------------------

	def scale(self, scale):
		self.print_x = scale * self.x
		self.print_y = scale * self.y
		self.print_w = scale * self.w
		self.print_h = scale * self.h

	def draw_skeleton(self, canvas):
		xy = (self.print_x, self.print_y)
		xY = (self.print_x, self.print_y + self.print_h - 1)
		Xy = (self.print_x + self.print_w - 1, self.print_y)
		XY = (self.print_x + self.print_w - 1, self.print_y + self.print_h - 1)

		color = random_color()

		draw = PIL.ImageDraw.Draw(canvas)
		draw.line(xy + Xy, fill=color)
		draw.line(xy + xY, fill=color)
		draw.line(xY + XY, fill=color)
		draw.line(Xy + XY, fill=color)
		draw.line(xy + XY, fill=color)
		draw.line(xY + Xy, fill=color)

	def draw_photo(self, canvas, w, h, x, y, fast):
		img = PIL.Image.open(self.imagefile)

		# Rotate image is EXIF says so
		if self.orientation == 3:
			img = img.rotate(180)
		elif self.orientation == 6:
			img = img.rotate(270)
		elif self.orientation == 8:
			img = img.rotate(90)

		if fast:
			method = PIL.Image.NEAREST
		else:
			method = PIL.Image.ANTIALIAS

		if img.size[0] * h > img.size[1] * w:
			# Image is too large
			img = img.resize((round(h * img.size[0] / img.size[1]), round(h)),
							 method)
			img.crop(((img.size[0] - w) / 2, 0, (img.size[0] + w) / 2, h))
		elif img.size[0] * h < img.size[1] * w:
			# Image is too high
			img = img.resize((round(w), round(w * img.size[1] / img.size[0])),
							 method)
			img.crop((0, (img.size[1] - h) / 2, w, (img.size[1] + h) / 2))
		else:
			img = img.resize((round(w), round(h)), method)
		canvas.paste(img, (round(x), round(y)))

class PhotoExtent(Photo):

	def __init__(self, img, x, y):
		self.img_ref = img
		super(PhotoExtent, self).__init__(img.imagefile, img.w, img.h, x, y)

class Column:

	def __init__(self, x, w):
		self.imglist = []
		self.x = x
		self.w = w
		self.h = 0

	# -------------------
	#  Phase B functions
	# -------------------

	def adjust_height(self, H):
		# Group "movable" zones together, spacings being non-movable
		groups = []
		groups.append({"imglist": []})
		groups[-1]["y"] = 0
		for img in self.imglist:
			if not isinstance(img, PhotoExtent):
				groups[-1]["imglist"].append(img)
			else:
				groups[-1]["h"] = img.y - groups[-1]["y"]
				groups.append({"imglist": []})
				groups[-1]["y"] = img.y + img.h
		groups[-1]["h"] = H - groups[-1]["y"]

		# Adjust height for each group independently
		for group in groups:
			if len(group["imglist"]) == 0:
				continue

			y = group["y"]
			alpha = group["h"] / sum(i.h for i in group["imglist"]) # enlargement
			for img in group["imglist"]:
				img.y = y
				img.h = img.h * alpha
				for s in img.spacings:
					s.y = img.y
					s.h = img.h
				img.x += (img.w - img.h * img.real_w / img.real_h) / 2
				img.w = img.h * img.real_w / img.real_h
				y += img.h

		self.h = H

	def get_width(self):
		"""Returns the width of the smallest image in this column"""
		imgs = list(img.w for img in self.imglist if not
					isinstance(img, PhotoExtent) and not img.extended)
		exts = list(img.w / 2 for img in self.imglist if
					not isinstance(img, PhotoExtent) and img.extended)
		spcs = list(img.img_ref.w / 2 for img in self.imglist if
					isinstance(img, PhotoExtent))
		mini = 2**32
		if len(imgs) > 0:
			mini = min(imgs)
		if len(exts) > 0:
			mini = min(mini, min(exts))
		if len(spcs) > 0:
			mini = min(mini, min(spcs))
		return mini

	def adjust_width(self):
		self.w = self.get_width()

		for img in self.imglist:
			if not isinstance(img, PhotoExtent) and not img.extended:
				img.x = self.x + (self.w - img.w) / 2
			elif not isinstance(img, PhotoExtent):
				img.x = self.x + (self.w - img.w) / 2
			else:
				img.img_ref.x += self.w / 2

	# -------------------
	#  Ranking functions
	# -------------------

	def wasted_space(self):
		waste = 0

		# Waste on left and right
		for img in self.imglist:
			if img.w < self.w:
				waste += img.h * (self.w - img.w)

		# Waste between non-adjacent images
		for i in range(len(self.imglist) - 1):
			img0 = self.imglist[i]
			img1 = self.imglist[i + 1]
			if img0.y + img0.h < img1.y:
				waste += self.w * (img1.y - (img0.y + img0.h))
		img0 = self.imglist[-1]
		if img0.y + img0.h < self.h:
			waste += self.w * (self.h - (img0.y + img0.h))

		return waste

	def hidden_space(self):
		hidden = 0

		# With current implementation, image can only overflow on left/right
		for img in self.imglist:
			if isinstance(img, PhotoExtent):
				if img.img_ref.x + img.img_ref.w > self.x + self.w:
					w = (img.img_ref.x + img.img_ref.w) - (self.x + self.w)
					hidden += w / img.img_ref.w
			else:
				if img.x < self.x:
					hidden += (self.x - img.x) / img.w

		return hidden

	# ---------------------
	#  Rendering functions
	# ---------------------

	def scale(self, scale):
		self.print_x = scale * self.x
		self.print_w = scale * self.w
		self.print_h = scale * self.h
		for img in self.imglist:
			img.scale(scale)

	def draw_skeleton(self, canvas):
		for img in self.imglist:
			if not isinstance(img, PhotoExtent):
				img.draw_skeleton(canvas)

	def draw_borders(self, canvas, border, color):
		draw = PIL.ImageDraw.Draw(canvas)

		for img in self.imglist[1:]:
			xy = (self.print_x, img.print_y - border / 2)
			XY = (self.print_x + self.print_w, img.print_y + border / 2)
			draw.rectangle(xy + XY, color)

		if self.print_x > 0:
			for img in self.imglist:
				if not isinstance(img, PhotoExtent):
					xy = (self.print_x - border / 2, img.print_y)
					XY = (self.print_x + border / 2, img.print_y + img.print_h)
					draw.rectangle(xy + XY, color)

	def draw_photos(self, canvas, fast):
		for img in self.imglist:
			if not isinstance(img, PhotoExtent):
				img.draw_photo(canvas, self.print_w, img.print_h,
							   self.print_x, img.print_y, fast)

class Page:

	def __init__(self, w, no_cols):
		self.w = w
		self.no_cols = no_cols
		self.cols = []

		x = 0
		col_w = self.w / self.no_cols
		for i in range(no_cols):
			self.cols.append(Column(x, col_w))
			x += col_w

	# -------------------
	#  Phase A functions
	# -------------------

	def next_col(self):
		cur_min = 2**31
		index = None
		for i in range(self.no_cols):
			if self.cols[i].h < cur_min:
				cur_min = self.cols[i].h
				index = i
		return index

	def worth_multicol(self):
		i = self.next_col()
		for j in range(max(0, i - 1), min(self.no_cols, i + 2)):
			if j == i:
				continue

			if abs(self.cols[j].h - self.cols[i].h) < 0.5 * self.cols[i].w:
				return sorted([i, j])

	def append(self, img):
		multicol = self.worth_multicol()
		if multicol and img.w / img.h > 1 and random.randint(0, 1):
			img.x = self.cols[multicol[0]].x
			img.y = max([self.cols[i].h for i in multicol])
			img.w = 0
			for i in multicol:
				img.w += self.cols[i].w
			img.h = img.w * img.real_h / img.real_w
			for i in multicol:
				if i == multicol[0]:
					img.extended = True
					self.cols[i].imglist.append(img)
				else:
					s = PhotoExtent(img, self.cols[i].x, self.cols[i].h)
					self.cols[i].imglist.append(s)
					img.spacings.append(s)
				self.cols[i].h = img.y + img.h # every column is set at the longest
		else:
			c = self.cols[self.next_col()]

			img.x = c.x
			img.y = c.h
			img.w = c.w
			img.h = c.w * img.real_h / img.real_w

			c.imglist.append(img)
			c.h += img.h

	def fill(self, imglist):
		for img in imglist:
			self.append(img)

	def get_width(self):
		return sum(c.w for c in self.cols)

	def get_height(self):
		return max(c.h for c in self.cols)

	# -------------------
	#  Phase B functions
	# -------------------

	def eat_space(self):
		H = sum([c.h for c in self.cols]) / self.no_cols
		for c in self.cols:
			c.adjust_height(H)

	# -------------------
	#  Phase C functions
	# -------------------

	def eat_space2(self):
		x = 0
		for c in self.cols:
			c.x = x
			c.adjust_width()
			x += c.w

	# -------------------
	#  Ranking functions
	# -------------------

	def wasted_space(self):
		return sum(c.wasted_space() for c in self.cols) / \
			   (self.get_width() * self.get_height())

	def hidden_space(self):
		return sum(c.hidden_space() for c in self.cols) / \
			   sum(len(c.imglist) for c in self.cols)

	# ---------------------
	#  Rendering functions
	# ---------------------

	def scale_to_fit(self, max_w, max_h):
		w = self.get_width()
		h = self.get_height()
		print("wh = (%f, %f)" % (w, h))
		if w * max_h > h * max_w:
			print("scale = %f" % (max_w / w))
			return max_w / w
		else:
			print("scale = %f" % (max_h / h))
			return max_h / h

	def scale(self, scale):
		self.print_w = scale * self.get_width()
		self.print_h = scale * self.get_height()
		for col in self.cols:
			col.scale(scale)

	def draw_skeleton(self, canvas):
		for col in self.cols:
			col.draw_skeleton(canvas)

	def draw_borders(self, canvas, border, color):
		W = self.print_w
		H = self.print_h

		draw = PIL.ImageDraw.Draw(canvas)
		draw.rectangle((0, 0) + (border, H), color)
		draw.rectangle((W - border, 0) + (W, H), color)
		draw.rectangle((0, 0) + (W, border), color)
		draw.rectangle((0, H - border) + (W, H), color)

		for col in self.cols:
			col.draw_borders(canvas, border, color)

	def draw_photos(self, canvas, fast):
		for col in self.cols:
			col.draw_photos(canvas, fast)

	def print(self, width, border, skeleton=False, fast=False):
		self.scale(width / self.get_width())

		canvas = PIL.Image.new("RGB", (int(self.print_w), int(self.print_h)),
							   "white")

		if skeleton:
			self.draw_skeleton(canvas)
		else:
			self.draw_photos(canvas, fast)
			self.draw_borders(canvas, border, "black")

		return canvas

class PreviewLabel(tk.Label):

	def __init__(self, master=None, **options):
		self.img = PIL.ImageTk.PhotoImage("RGB", (300, 300))
		self.img.paste(PIL.Image.new("RGB", (300, 300), "gray"))

		return super(PreviewLabel, self).__init__(master, options, image=self.img)

	def set_img(self, img):
		canvas = PIL.Image.new("RGB", (300, 300), "gray")

		w, h = img.size
		x = y = 0
		if w > h:
			y = round((300 - h) / 2)
		else:
			x = round((300 - w) / 2)

		canvas.paste(img, (x, y))

		self.img.paste(canvas)

class PosterMakerGUI(tk.Frame):

	def __init__(self, master=None):
		tk.Frame.__init__(self, master)
		self.pack()
		self.createWidgets()
		self.master.title("PosterMaker")

	def createWidgets(self):
		pan_root = tk.PanedWindow()
		pan_root.pack(fill=tk.BOTH, expand=1)

		self.pan_settings = tk.PanedWindow(pan_root, orient=tk.VERTICAL)
		self.pan_skeleton = tk.PanedWindow(pan_root, orient=tk.VERTICAL)
		self.pan_preview = tk.PanedWindow(pan_root, orient=tk.VERTICAL)
		pan_root.add(self.pan_settings)
		pan_root.add(self.pan_skeleton)
		pan_root.add(self.pan_preview)

		# -----------
		#  First pan
		# -----------

		self.QUIT = tk.Button(self.pan_settings, text="Chose images", command=self.select_files)
		self.pan_settings.add(self.QUIT)

		# ------------
		#  Second pan
		# ------------

		self.btn_skeleton = tk.Button(self.pan_skeleton, text="Generate a new layout", command=self.make_skeleton, state="disabled")
		self.pan_skeleton.add(self.btn_skeleton)
		self.lbl_skeleton = PreviewLabel(self.pan_skeleton, width=300, height=300)
		self.pan_skeleton.add(self.lbl_skeleton)

		# -----------
		#  Third pan
		# -----------

		self.btn_preview = tk.Button(self.pan_preview, text="Preview poster", command=self.make_preview, state="disabled")
		self.pan_preview.add(self.btn_preview)
		self.lbl_preview = PreviewLabel(self.pan_preview, width=300, height=300)
		self.pan_preview.add(self.lbl_preview)

	def build_photolist(self, filelist):
		ret = []

		for name in filelist:
			img = PIL.Image.open(name)
			w, h = img.size

			try:
				exif = img._getexif()
				if 274 in exif: # orientation tag
					orientation = exif[274]
					if orientation == 6 or orientation == 8:
						w, h = h, w
			except:
				orientation = 0

			photo = Photo(name, w, h)
			photo.orientation = orientation

			ret.append(photo)

		return ret

	def select_files(self):
		filelist = tk.filedialog.askopenfilenames(parent=self, title="Choose a file")
		for a in filelist:
			print(a)
		self.photolist = self.build_photolist(filelist)

		self.btn_skeleton.config(state="disabled")
		self.btn_preview.config(state="disabled")
		if len(self.photolist) > 0:
			self.btn_skeleton.config(state="normal")

	def make_skeleton(self):
		#photolist = fake_images()

		random.shuffle(self.photolist)

		no_cols = int(math.sqrt(len(self.photolist)))

		self.page = Page(1.0, no_cols)
		self.page.fill(copy.deepcopy(self.photolist))
		self.page.eat_space()
		self.page.eat_space2()

		img = self.page.print(self.page.scale_to_fit(300, 300), 6, True)

		self.lbl_skeleton.set_img(img)

		self.btn_preview.config(state="normal")

	def make_preview(self):
		img = self.page.print(self.page.scale_to_fit(300, 300), 6, False, True)

		self.lbl_preview.set_img(img)

def fake_images():
	ret = []
	for i in range(random.randint(10, 60)):
		ret.append(Photo(None, 1000, 1000 * (.5 + random.random())))
	return ret

def main():
	root = tk.Tk()
	app = PosterMakerGUI(root)
	app.mainloop()
	root.destroy()
	return

	photolist = fake_images()

	tries = []
	best_no_cols = int(math.sqrt(len(photolist)))
	for no_cols in range(max(1, best_no_cols - 1), best_no_cols + 3):
		for i in range(1):
			page = Page(1.0, no_cols)
			random.shuffle(photolist)
			page.fill(copy.deepcopy(photolist))
			page.eat_space()
			page.eat_space2()
			if page.wasted_space() < 0.001:
				tries.append(page)

	tries.sort(key=lambda t: t.hidden_space())

	page = tries[0]
	print("wasted space: %.2f%% + %.2f%%" % (100*page.wasted_space(), 100*page.hidden_space()))

	page.print(600 * page.get_width() / page.get_height(), 6, True).save("page-best-preview.png")
	page.print(600 * page.get_width() / page.get_height(), 6).save("page-best.jpg", quality=90, optimize=True)

	page = tries[-1]
	print("wasted space: %.2f%% + %.2f%%" % (100*page.wasted_space(), 100*page.hidden_space()))
	page.print(600 * page.get_width() / page.get_height(), 6, True).save("page-worst-preview.png")
	page.print(600 * page.get_width() / page.get_height(), 6).save("page-worst.jpg", quality=90, optimize=True)

if __name__ == "__main__":
	main()
