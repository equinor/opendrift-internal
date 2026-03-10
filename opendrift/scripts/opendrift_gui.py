#!/usr/bin/env python

import matplotlib
from matplotlib import pyplot as plt
if __name__ == '__main__':
    matplotlib.use('TKAgg')

import sys
import logging
import os
import argparse
from datetime import datetime, timedelta
import numpy as np

from PIL import ImageTk, Image
logging.getLogger('PIL').setLevel(logging.INFO)
import tkinter as tk
from tkinter import ttk, messagebox
from importlib.resources import files
import opendrift
from opendrift.models.oceandrift import OceanDrift
from opendrift.models.openoil import OpenOil
from opendrift.models.leeway import Leeway
from opendrift.models.shipdrift import ShipDrift
from opendrift.models.openberg import OpenBerg
from opendrift.models.plastdrift import PlastDrift
from opendrift.models.radionuclides import RadionuclideDrift
from opendrift.models.basemodel import Mode

# Class to redirect output to text box
class TextRedirector:

    def __init__(self, widget, tag='stdout'):
        self.defstdout = sys.stdout
        self.widget = widget
        self.tag = tag

    def write(self, str):
        self.widget.configure(state='normal')
        self.widget.insert('end', str, (self.tag,))
        self.widget.update_idletasks()
        self.widget.see(tk.END)

    def flush(self):
        self.defstdout.flush()

# Class for help-text
# https://stackoverflow.com/questions/20399243/display-message-when-hovering-over-something-with-mouse-cursor-in-python
class ToolTip(object):

    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text):
        "Display text in tooltip window"
        self.text = text
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 57
        y = y + cy + self.widget.winfo_rooty() +27
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                      background="#ffff00", relief=tk.SOLID, borderwidth=1,
                      font=("tahoma", "10", "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

def CreateToolTip(widget, text):
    toolTip = ToolTip(widget)
    def enter(event):
        toolTip.showtip(text)
    def leave(event):
        toolTip.hidetip()
    widget.bind('<Enter>', enter)
    widget.bind('<Leave>', leave)


class OpenDriftGUI(tk.Tk):

    # Supported models as dictionary {model_name:model_class}
    opendrift_models = {m.__name__:m for m in
        [Leeway, OpenOil, ShipDrift, OpenBerg, OceanDrift, PlastDrift, RadionuclideDrift]}

    extra_args = {'OpenOil': {'location': 'NORWAY'}}

    # Overriding some default config settings, suitable for GUI
    # TODO: should be set as default-default
    GUI_config = {
            'general:time_step_minutes': {'default': 15, 'min': 1},
            'general:time_step_output_minutes': {'default': 30, 'min': 5},
            'seed:number': {'default': 5000, 'max': 100000},
            'seed:m3_per_hour': {'default': 100}
            }

    def __init__(self, forcing_files):

        self.forcing_files = forcing_files

        tk.Tk.__init__(self)

        self.title('OpenDrift ' + opendrift.__version__ + ' - Simulation GUI')
        
        # Allow window to be resized and scrolled on smaller screens
        self.resizable(True, True)
        self.minsize(700, 600)
        # Set initial window size to show full content including output
        self.geometry('700x800')
        
        # Apply modern ttk theme with white background
        style = ttk.Style()
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'alt' in available_themes:
            style.theme_use('alt')

        # Modern font
        modern_font = ('Microsoft JhengHei UI Light', 10)
        modern_font_small = ('Microsoft JhengHei UI Light', 9)
        modern_font_bold = ('Microsoft JhengHei UI', 10)
        self.modern_font = modern_font
        self.modern_font_small = modern_font_small
        self.option_add('*Font', modern_font)
        self.option_add('*TkDefaultFont', modern_font)

        # Set white background for all widgets
        self.configure(bg='white')
        style.configure('.', background='white', font=modern_font)
        style.configure('TFrame', background='white')
        style.configure('TLabel', background='white', font=modern_font)
        style.configure('TLabelframe', background='white')
        style.configure('TLabelframe.Label', background='white', font=modern_font_bold)
        style.configure('TNotebook', background='white')
        style.configure('TNotebook.Tab', background='#f0f0f0', font=modern_font,
                        padding=[12, 4])
        style.map('TNotebook.Tab',
                  background=[('selected', 'white')],
                  foreground=[('selected', 'black')])
        style.configure('TCheckbutton', background='white', font=modern_font)
        style.configure('TRadiobutton', background='white', font=modern_font)
        style.configure('TButton', font=modern_font, padding=[8, 4],
                        background='#e8e8e8', borderwidth=1, relief='raised')
        style.map('TButton',
                  background=[('active', '#d0d0d0'), ('pressed', '#c0c0c0')],
                  relief=[('pressed', 'sunken'), ('!pressed', 'raised')])
        style.configure('TEntry', fieldbackground='#E8F0FE')
        style.configure('TCombobox', fieldbackground='#E8F0FE')
        # Light blue background for input highlighting
        self.input_bg = '#E8F0FE'

        ##################
        # Layout frames
        ##################
        self.n = ttk.Notebook(self)
        self.n.grid(row=0, column=0, sticky='nsew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Create a scrollable container for the Seeding tab
        seed_container = ttk.Frame(self.n)
        self.seed_canvas = tk.Canvas(seed_container, highlightthickness=0, bg='white')
        self.seed_scrollbar = ttk.Scrollbar(seed_container, orient="vertical",
                                            command=self.seed_canvas.yview)
        self.seed = ttk.Frame(self.seed_canvas)
        
        self.seed.bind(
            "<Configure>",
            lambda e: self.seed_canvas.configure(
                scrollregion=self.seed_canvas.bbox("all"))
        )
        self.seed_canvas_window = self.seed_canvas.create_window(
            (0, 0), window=self.seed, anchor="nw")
        self.seed_canvas.configure(yscrollcommand=self.seed_scrollbar.set)
        
        self.seed_canvas.pack(side="left", fill="both", expand=True)
        self.seed_scrollbar.pack(side="right", fill="y")
        
        # Update canvas width when container resizes
        def _on_seed_container_configure(event):
            self.seed_canvas.itemconfig(
                self.seed_canvas_window, width=event.width)
        self.seed_canvas.bind("<Configure>", _on_seed_container_configure)
        
        # Mousewheel scrolling for the seed tab
        def _on_seed_mousewheel(event):
            self.seed_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.seed_canvas.bind("<MouseWheel>", _on_seed_mousewheel)
        self.seed.bind("<MouseWheel>", _on_seed_mousewheel)
        # Also bind to all child widgets as they are added
        def _bind_mousewheel_recursive(widget, handler):
            widget.bind("<MouseWheel>", handler)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child, handler)
        self._bind_seed_mousewheel = lambda: _bind_mousewheel_recursive(self.seed, _on_seed_mousewheel)
        self._on_seed_mousewheel = _on_seed_mousewheel
        
        self.confignotebook = ttk.Notebook(self.n)
        self.config = ttk.Frame(self.confignotebook)
        self.forcing = ttk.Frame(self.n)
        self.n.add(seed_container, text='Seeding')
        self.n.add(self.confignotebook, text='Config')
        self.n.add(self.forcing, text='Forcing')
        self.confignotebook.add(self.config, text='SubConfig')

        # Top
        self.logo = tk.Frame(self.seed, bg='white')
        self.logo.grid(row=0, column=0, rowspan=1)
        self.top = ttk.Frame(self.seed, padding=(25, 25))
        self.top.grid(row=0, column=1, rowspan=1)

        # Combined Release LabelFrame
        self.release_frame = ttk.LabelFrame(self.seed, text='RELEASE', padding=(10, 10))
        self.release_frame.grid(row=20, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        
        # Sub-labels for Start and End inside the combined frame
        self.start_t = ttk.Frame(self.release_frame)
        self.start_t.grid(row=0, column=0, rowspan=1)
        self.start = ttk.LabelFrame(self.release_frame, text='START', padding=(5, 5))
        self.start.grid(row=0, column=1, rowspan=1, padx=5, pady=(0, 5))
        self.end_t = ttk.Frame(self.release_frame)
        self.end_t.grid(row=1, column=0, rowspan=1)
        self.end = ttk.LabelFrame(self.release_frame, text='END', padding=(5, 5))
        self.end.grid(row=1, column=1, padx=5, pady=(0, 5))
        
        self.coastline = ttk.Frame(self.seed, padding=(5, 0))
        self.coastline.grid(row=40, column=1)
        self.duration = ttk.Frame(self.seed, padding=(5, 5))
        self.duration.grid(row=50, column=1)
        
        # Results frame - placed above output, visible after simulation
        self.results = ttk.Frame(self.seed, padding=(5, 0))
        self.results.grid(row=70, column=0, columnspan=2, sticky='ew')

        # Output frame - guaranteed minimum size
        self.output = ttk.LabelFrame(self.seed, text='OUTPUT LOG', padding=(5, 5))
        self.output.grid(row=80, column=0, columnspan=2, sticky='ew', padx=5, pady=5)

        #######################################################
        ttk.Label(self.top, text='Simulation type').grid(row=0, column=0)
        self.model = tk.StringVar()
        self.model.set(list(self.opendrift_models)[0])
        self.modeldrop = ttk.OptionMenu(self.top, self.model,
            list(self.opendrift_models)[0], *list(self.opendrift_models), command=self.set_model)
        self.modeldrop.grid(row=0, column=1, padx=5)

        help_button = ttk.Button(self.top, text='Help',
                                 command=self.show_help)
        help_button.grid(row=0, column=2, padx=50)


        ##########
        # Release
        ##########
        startlabel = ttk.Label(self.start_t, text='Start release')
        startlabel.grid(row=0, column=0, pady=5)

        ttk.Label(self.start, text='Longitude').grid(row=0, column=1)
        ttk.Label(self.start, text='Latitude').grid(row=0, column=0)
        ttk.Label(self.start, text='Radius [m]').grid(row=0, column=2)
        self.latvar = tk.StringVar()
        self.lonvar = tk.StringVar()
        self.radiusvar = tk.StringVar()
        self.lat = ttk.Entry(self.start, textvariable=self.latvar,
                             width=10, justify=tk.RIGHT)
        self.lon = ttk.Entry(self.start, textvariable=self.lonvar,
                             width=10, justify=tk.RIGHT)
        self.radius = ttk.Entry(self.start, width=6,
                                textvariable=self.radiusvar,
                                justify=tk.RIGHT)
        self.lon.grid(row=10, column=1)
        self.lon.insert(0, '4.5')
        self.lat.grid(row=10, column=0)
        self.lat.insert(0, '60.0')
        self.radius.grid(row=10, column=2)
        self.radius.insert(0, '1000')
        self.lonvar.trace('w', self.copy_position)
        self.latvar.trace('w', self.copy_position)
        self.radiusvar.trace('w', self.copy_position)
        conv=ttk.Label(self.start, text='Convert from deg/min/sec', foreground='blue', cursor='hand2')
        conv.grid(row=11, column=0, columnspan=2)
        conv.bind("<Button-1>", lambda e: self.convert_lonlat())

        ##########
        # Time
        ##########
        now = datetime.utcnow()
        ttk.Label(self.start, text='Day').grid(row=20, column=0)
        ttk.Label(self.start, text='Month').grid(row=20, column=1)
        ttk.Label(self.start, text='Year').grid(row=20, column=2)
        ttk.Label(self.start, text='Hour').grid(row=20, column=3)
        ttk.Label(self.start, text='Minutes').grid(row=20, column=4)
        ttk.Label(self.start, text='Timezone').grid(row=0, column=4)
        self.datevar = tk.StringVar()
        self.dates = range(1, 32)
        self.datevar.set(now.day)
        self.date = tk.OptionMenu(self.start, self.datevar, *self.dates)
        self.date.config(bg=self.input_bg, highlightthickness=0)
        self.date.grid(row=30, column=0)

        self.monthvar = tk.StringVar()
        self.months = ['January', 'February', 'March', 'April', 'May',
                       'June', 'July', 'August', 'September', 'October',
                       'November', 'December']
        self.monthvar.set(self.months[now.month-1])
        self.month = tk.OptionMenu(self.start, self.monthvar,
                                   *self.months)
        self.month.config(bg=self.input_bg, highlightthickness=0)
        self.month.grid(row=30, column=1)

        self.yearvar = tk.StringVar()
        self.years = range(2015, now.year+2)
        self.yearvar.set(now.year)
        self.year = tk.OptionMenu(self.start, self.yearvar, *self.years)
        self.year.config(bg=self.input_bg, highlightthickness=0)
        self.year.grid(row=30, column=2)

        self.hourvar = tk.StringVar()
        self.hours = range(0, 24)
        self.hourvar.set(now.hour)
        self.hour = tk.OptionMenu(self.start, self.hourvar, *self.hours)
        self.hour.config(bg=self.input_bg, highlightthickness=0)
        self.hour.grid(row=30, column=3)

        self.minutevar = tk.StringVar()
        self.minutes = range(0, 60, 5)
        self.minutevar.set(now.minute)
        self.minute = tk.OptionMenu(self.start, self.minutevar,
                                    *self.minutes)
        self.minute.config(bg=self.input_bg, highlightthickness=0)
        self.minute.grid(row=30, column=4)

        self.timezonevar = tk.StringVar()
        self.timezone = ['UTC', 'CET']
        self.timezonevar.set('UTC')
        self.timezone = tk.OptionMenu(self.start, self.timezonevar,
                                    *self.timezone)
        self.timezone.config(bg=self.input_bg, highlightthickness=0)
        self.timezone.grid(row=10, column=4)

        self.datevar.trace('w', self.copy_position)
        self.monthvar.trace('w', self.copy_position)
        self.yearvar.trace('w', self.copy_position)
        self.hourvar.trace('w', self.copy_position)
        self.minutevar.trace('w', self.copy_position)

        ###############
        # Release End
        ###############
        endlabel = ttk.Label(self.end_t, text='End release')
        endlabel.grid(row=0, column=0, pady=5)
        ttk.Label(self.end, text='Longitude').grid(row=0, column=1)
        ttk.Label(self.end, text='Latitude').grid(row=0, column=0)
        ttk.Label(self.end, text='Radius [m]').grid(row=0, column=2)
        self.elat = ttk.Entry(self.end, width=10, justify=tk.RIGHT)
        self.elon = ttk.Entry(self.end, width=10, justify=tk.RIGHT)
        self.eradius = ttk.Entry(self.end, width=6, justify=tk.RIGHT)
        self.elon.grid(row=10, column=1)
        self.elon.insert(0, '4.5')
        self.elat.grid(row=10, column=0)
        self.elat.insert(0, '60.0')
        self.eradius.grid(row=10, column=2)
        self.eradius.insert(0, '1000')
        ##########
        # Time
        ##########
        now = datetime.utcnow()
        ttk.Label(self.end, text='Day').grid(row=20, column=0)
        ttk.Label(self.end, text='Month').grid(row=20, column=1)
        ttk.Label(self.end, text='Year').grid(row=20, column=2)
        ttk.Label(self.end, text='Hour').grid(row=20, column=3)
        ttk.Label(self.end, text='Minutes').grid(row=20, column=4)
        self.edatevar = tk.StringVar()
        self.edates = range(1, 32)
        self.edatevar.set(now.day)
        self.edate = tk.OptionMenu(self.end, self.edatevar, *self.edates)
        self.edate.config(bg=self.input_bg, highlightthickness=0)
        self.edate.grid(row=30, column=0)

        self.emonthvar = tk.StringVar()
        self.emonthvar.set(self.months[now.month-1])
        self.emonth = tk.OptionMenu(self.end, self.emonthvar,
                                    *self.months)
        self.emonth.config(bg=self.input_bg, highlightthickness=0)
        self.emonth.grid(row=30, column=1)

        self.eyearvar = tk.StringVar()
        self.eyears = range(2015, now.year+2)
        self.eyearvar.set(now.year)
        self.eyear = tk.OptionMenu(self.end, self.eyearvar, *self.eyears)
        self.eyear.config(bg=self.input_bg, highlightthickness=0)
        self.eyear.grid(row=30, column=2)

        self.ehourvar = tk.StringVar()
        self.ehours = range(0, 24)
        self.ehourvar.set(now.hour)
        self.ehour = tk.OptionMenu(self.end, self.ehourvar, *self.ehours)
        self.ehour.config(bg=self.input_bg, highlightthickness=0)
        self.ehour.grid(row=30, column=3)

        self.eminutevar = tk.StringVar()
        self.eminutes = range(0, 60, 5)
        self.eminutevar.set(now.minute)
        self.eminute = tk.OptionMenu(self.end, self.eminutevar,
                                     *self.eminutes)
        self.eminute.config(bg=self.input_bg, highlightthickness=0)
        self.eminute.grid(row=30, column=4)
        self.eyear.config(state='normal')
        self.emonth.config(state='normal')
        self.edate.config(state='normal')
        self.ehour.config(state='normal')
        self.eminute.config(state='normal')

        # Check seeding
        check_seed = ttk.Button(self.end_t, text='Check seeding',
                                command=self.check_seeding)
        check_seed.grid(row=10, column=0, padx=5, pady=5)

        #######################
        # Simulation duration
        #######################
        ttk.Label(self.duration, text='Run simulation ').grid(row=50, column=0)
        self.durationhours = ttk.Entry(self.duration, width=3,
                                       justify=tk.RIGHT)
        self.durationhours.grid(row=50, column=1)
        self.durationhours.insert(0, 12)
        ttk.Label(self.duration, text=' hours ').grid(row=50, column=2)

        self.directionvar = tk.StringVar()
        self.directionvar.set('forwards')
        self.direction = tk.OptionMenu(self.duration, self.directionvar,
                                       'forwards', 'backwards')
        self.direction.config(bg=self.input_bg, highlightthickness=0)
        self.direction.grid(row=50, column=3)
        ttk.Label(self.duration, text=' in time ').grid(row=50, column=4)

        ##############
        # Output box
        ##############
        # Text widget with fixed height - always visible
        self.text = tk.Text(self.output, wrap="word", height=18, font=('Consolas', 10), bg='white')
        self.text.grid(row=0, column=0, sticky='ew')
        self.text.tag_configure("stderr", foreground="#b22222")
        if os.getenv('OPENDRIFT_GUI_OUTPUT', 'gui') == 'gui':
            sys.stdout = TextRedirector(self.text, "stdout")
            sys.stderr = TextRedirector(self.text, "stderr")
        s = ttk.Scrollbar(self.output, command=self.text.yview)
        s.grid(row=0, column=1, sticky='ns')
        self.text.config(yscrollcommand=s.set)
        
        # Utility buttons below output
        button_frame = ttk.Frame(self.output)
        button_frame.grid(row=1, column=0, sticky='w', pady=(5, 0))
        ttk.Button(button_frame, text='Clear Output', 
                   command=self.clear_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text='Copy Output', 
                   command=self.copy_output).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text='Save Log', 
                   command=self.save_log).pack(side=tk.LEFT, padx=2)

        # Diana
        self.dianadir = '/vol/vvfelles/opendrift/output/'
        if os.path.exists(self.dianadir):
            self.has_diana = True
            print('Diana is available!')
            self.outputdir = '/vol/vvfelles/opendrift/output_native/'
            startbutton = 'PEIS PAO'
        else:
            self.has_diana = False
            startbutton = 'START'

        ##############
        # Initialise
        ##############
        self.set_model(list(self.opendrift_models)[0])

        # Create scrollable forcing display
        forcing_canvas = tk.Canvas(self.forcing, highlightthickness=0, bg='white')
        forcing_scrollbar = ttk.Scrollbar(self.forcing, orient="vertical", command=forcing_canvas.yview)
        forcing_frame = ttk.Frame(forcing_canvas)
        
        forcing_frame.bind(
            "<Configure>",
            lambda e: forcing_canvas.configure(scrollregion=forcing_canvas.bbox("all"))
        )
        
        forcing_canvas.create_window((0, 0), window=forcing_frame, anchor="nw")
        forcing_canvas.configure(yscrollcommand=forcing_scrollbar.set)
        
        forcing_canvas.pack(side="left", fill="both", expand=True)
        forcing_scrollbar.pack(side="right", fill="y")
        
        # Enable mousewheel scrolling for forcing
        def _on_forcing_mousewheel(event):
            forcing_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        forcing_canvas.bind("<MouseWheel>", _on_forcing_mousewheel)
        forcing_frame.bind("<MouseWheel>", _on_forcing_mousewheel)
        
        for i, ff in enumerate(self.forcing_files):
            ttk.Label(forcing_frame, text=ff.strip(), wraplength=650, 
                     font=('Consolas', 9)).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)

        ##########################
        try:
            if datetime.now().month == 12 and datetime.now().day > 10:
                img = ImageTk.PhotoImage(Image.open(
                    opendrift.test_data_folder +
                                         '../../docs/hohohOpenDrift.jpg').resize((200, 200)))
                try:
                    self.seed.configure(background='lightblue')
                except:
                    pass  # ttk frames may not support bg
            else:
                img = ImageTk.PhotoImage(Image.open(
                    opendrift.test_data_folder +
                                         '../../docs/opendrift_logo.png'))
            self.logo_image=tk.Label(self.logo, image=img)
            self.logo_image.image = img
            self.logo_image.grid(row=0, column=0)
        except Exception as e:
            print(e)
            pass # Could not display logo

        ##########
        # RUN and Control Buttons
        ##########
        control_frame = ttk.Frame(self.seed)
        control_frame.grid(row=60, column=1, sticky='w', pady=4)
        
        # Start button with green color (uses tk.Button for reliable color on Windows)
        self.start_btn = tk.Button(control_frame, text=startbutton, 
                               command=self.run_opendrift,
                               bg='#4CAF50', fg='white', activebackground='#45a049',
                               activeforeground='white', font=('Microsoft JhengHei UI', 11),
                               relief=tk.RAISED, width=12, pady=4, cursor='hand2',
                               disabledforeground='black', bd=2)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        # Additional control buttons
        ttk.Button(control_frame, text='Reset to Defaults',
                   command=self.reset_defaults).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text='Load Settings',
                   command=self.load_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text='Save Settings',
                   command=self.save_settings).pack(side=tk.LEFT, padx=5)

        try:
            import opendrift_gui_conf
            opendrift_gui_conf.customize(self)
        except Exception as e:
            print('No custom configuration')
            #print(e)

    def copy_position(self, a, b, c):
        self.elat.delete(0, tk.END)
        self.elat.insert(0, self.lat.get())
        self.elon.delete(0, tk.END)
        self.elon.insert(0, self.lon.get())
        self.eradius.delete(0, tk.END)
        self.eradius.insert(0, self.radius.get())
        self.edatevar.set(self.datevar.get())
        self.emonthvar.set(self.monthvar.get())
        self.eyearvar.set(self.yearvar.get())
        self.ehourvar.set(self.hourvar.get())
        self.eminutevar.set(self.minutevar.get())

    def handle_result(self, command):

        mode = self.o.mode  # To be reset after plotting
        self.o.mode = Mode.Result
        from os.path import expanduser
        from tkinter import filedialog
        from pathlib import Path
        homefolder = expanduser("~")
        default_name = self.simulationname

        if command[0:4] == 'save':
            plt.switch_backend('agg')
        elif command[0:4] == 'show':
            plt.switch_backend('TkAgg')

        if command == 'saveanimation':
            filename = filedialog.asksaveasfilename(
                initialdir=Path.home(), initialfile=default_name + '.mp4',
                defaultextension='.mp4',
                filetypes=[('MP4 video', '*.mp4'), ('GIF animation', '*.gif'), ('All files', '*.*')])
            if not filename:
                self.o.mode = mode
                return
            self.o.animation(filename=filename)
            print('='*30 + '\nAnimation saved to file:\n'
                  + filename + '\n' + '='*30)
        elif command == 'showanimation':
            self.o.animation()
        elif command == 'saveplot':
            filename = filedialog.asksaveasfilename(
                initialdir=Path.home(), initialfile=default_name + '.png',
                defaultextension='.png',
                filetypes=[('PNG image', '*.png'), ('PDF document', '*.pdf'), ('All files', '*.*')])
            if not filename:
                self.o.mode = mode
                return
            self.o.plot(filename=filename)
            print('='*30 + '\nPlot saved to file:\n'
                  + filename + '\n' + '='*30)
        elif command == 'showplot':
            self.o.plot()
        elif command == 'showoilbudget':
            self.o.plot_oil_budget()
        elif command == 'saveoilbudget':
            filename = filedialog.asksaveasfilename(
                initialdir=Path.home(), initialfile=default_name + '_oilbudget.png',
                defaultextension='.png',
                filetypes=[('PNG image', '*.png'), ('PDF document', '*.pdf'), ('All files', '*.*')])
            if not filename:
                self.o.mode = mode
                return
            self.o.plot_oil_budget(filename=filename)
            print('='*30 + '\nPlot saved to file: '
                  + filename + '\n' + '='*30)

        elif command == 'showanimationspecie':
            self.o.animation(
                color='specie',vmin=0,vmax=self.o.nspecies-1,
                colorbar=False,
                legend=[self.o.specie_num2name(i) for i in range(self.o.nspecies)]
                )
        elif command == 'saveanimationspecie':
            filename = filedialog.asksaveasfilename(
                initialdir=Path.home(), initialfile=default_name + '_specie.mp4',
                defaultextension='.mp4',
                filetypes=[('MP4 video', '*.mp4'), ('All files', '*.*')])
            if not filename:
                self.o.mode = mode
                return
            self.o.animation(filename=filename,
                color='specie',vmin=0,vmax=self.o.nspecies-1,
                                colorbar=False,
                legend=[self.o.specie_num2name(i) for i in range(self.o.nspecies)]
                )
        elif command == 'saveconcfile':
            filename = filedialog.asksaveasfilename(
                initialdir=Path.home(), initialfile='conc_radio.nc',
                defaultextension='.nc',
                filetypes=[('NetCDF files', '*.nc'), ('All files', '*.*')])
            if not filename:
                self.o.mode = mode
                return
            self.o.guipp_saveconcfile(filename=filename)
        elif command == 'plotconc':
            zlayer = [-1]
            time   = None
            specie = ['LMM']
            self.o.guipp_plotandsaveconc(filename=homefolder+'/conc_radio.nc',
                                         outfilename=homefolder+'/radio_plots/RadioConc',
                                         zlayers=zlayer, time=time, specie=specie )
        elif command == 'showanimationprofile':
            self.o.guipp_showanimationprofile()
        elif command == 'copy_netcdf':
            import shutil
            from tkinter import filedialog
            import pathlib
            folder_selected = filedialog.askdirectory(initialdir=pathlib.Path.home())
            try:
                shutil.copy(self.o.outfile_name, folder_selected)
                print('Copied netCDF file to:\n' \
                      f'{folder_selected}/{os.path.basename(self.o.outfile_name)}')
            except Exception as e:
                print('Could not copy file:')
                print(e)

        self.o.mode = mode  # resetting

    def validate_config(self, value_if_allowed, prior_value, key):
        """From config menu selection."""
        if value_if_allowed == 'None':
            return True
        if value_if_allowed in ' -':
            return True
        sc = self.o._config[key]
        if sc['type'] in ['int', 'float']:
            try:
                value_if_allowed = float(value_if_allowed)
            except:
                return False

        try:
            self.o.set_config(key, value_if_allowed)
            return True
        except Exception as e:
            print(e)
            return False

    def set_model(self, model, rebuild_gui=True, logfile=None):

        # Creating simulation object (self.o) of chosen model class
        print('Setting model: ' + model)
        if model in self.extra_args:
            extra_args = self.extra_args[model]
        else:
            extra_args = {}
        terminal_output = [logging.StreamHandler(sys.stdout)]
        if logfile is None:
            logfile = terminal_output
        else:
            logfile = [logfile] + terminal_output
        self.o = self.opendrift_models[model](**extra_args, logfile=logfile)
        self.modelname = model  # So that new instance may be initiated at repeated run

        # Setting GUI-specific default config values
        for k,v in self.GUI_config.items():
            try:
                if 'default' in v:
                    self.o._set_config_default(k, v['default'])
                if 'min' in v:
                    self.o._config[k]['min'] = v['min']
                if 'max' in v:
                    self.o._config[k]['max'] = v['max']
            except:
                pass

        if rebuild_gui is False:
            return

        # Remove current GUI components and rebuild with new
        for con in self.confignotebook.winfo_children():
            con.destroy()
        self.subconfig = {}
        confnames = list(set([cn.split(':')[0] for cn in self.o._config]))
        confnames.extend(['environment:constant', 'environment:fallback'])
        confnames.remove('environment')
        
        # Create scrollable frames for each config tab
        for sub in confnames:
            # Create container with canvas and scrollbar
            container = ttk.Frame(self.confignotebook)
            canvas = tk.Canvas(container, highlightthickness=0, bg='white')
            scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
            self.subconfig[sub] = ttk.Frame(canvas, padding=(10, 10))
            
            self.subconfig[sub].bind(
                "<Configure>",
                lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=self.subconfig[sub], anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # Enable mousewheel scrolling per-canvas (not bind_all)
            def _on_mousewheel(event, canvas=canvas):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            canvas.bind("<MouseWheel>", _on_mousewheel)
            self.subconfig[sub].bind("<MouseWheel>", _on_mousewheel)
            
            self.confignotebook.add(container, text=sub)

        sc = self.o.get_configspec(level=[2, 3])
        self.config_input = {}
        self.config_input_var = {}
        for i, key in enumerate(list(sc)):
            if key.startswith('environment:constant'):
                tab = self.subconfig['environment:constant']
                keystr = key.split(':')[-1]
            elif key.startswith('environment:fallback'):
                tab = self.subconfig['environment:fallback']
                keystr = key.split(':')[-1]
            else:
                tab = self.subconfig[key.split(':')[0]]
                keystr = ''.join(key.split(':')[1:])
            if keystr == '':
                keystr = key
            lab = ttk.Label(tab, text=keystr)
            lab.grid(row=i, column=1, rowspan=1, sticky='w', padx=5, pady=2)
            if sc[key]['type'] in ['float', 'int']:
                self.config_input_var[i] = tk.StringVar()
                vcmd = (tab.register(self.validate_config),
                    '%P', '%s', key)
                self.config_input[i] = ttk.Entry(
                    tab, textvariable=self.config_input_var[i],
                    validate='key', validatecommand=vcmd,
                    width=12, justify=tk.RIGHT)
                self.config_input[i].insert(0, str(sc[key]['default']))
                self.config_input[i].grid(row=i, column=2, rowspan=1, padx=5)
                ttk.Label(tab, text='[%s]  min: %s, max: %s' % (
                    sc[key]['units'], sc[key]['min'], sc[key]['max'])
                        ).grid(row=i, column=3, rowspan=1, sticky='w', padx=5)
            if sc[key]['type'] == 'str':
                self.config_input_var[i] = tk.StringVar()
                vcmd = (tab.register(self.validate_config),
                    '%P', '%s', key)
                max_length = sc[key].get('max_length') or 12
                max_length = np.minimum(max_length, 64)
                self.config_input[i] = ttk.Entry(
                    tab, textvariable=self.config_input_var[i],
                    validate='key', validatecommand=vcmd,
                    width=max_length, justify=tk.RIGHT)
                self.config_input[i].insert(0, str(sc[key]['default']))
                self.config_input[i].grid(row=i, column=2, columnspan=3, rowspan=1, padx=5)
                #ttk.Label(tab, text='').grid(row=i, column=3, rowspan=1)
            elif sc[key]['type'] == 'bool':
                if self.o.get_config(key) is True:
                    value = 1
                else:
                    value = 0
                self.config_input_var[i] = tk.IntVar(value=value)
                vcb = (tab.register(self.set_config_checkbox),
                       key, i)
                self.config_input[i] = ttk.Checkbutton(
                    tab, variable=self.config_input_var[i],
                    command=vcb, text='')
                self.config_input[i].grid(row=i, column=2, rowspan=1, sticky='w', padx=5)
            elif sc[key]['type'] == 'enum':
                self.config_input_var[i] = tk.StringVar(value=self.o.get_config(key))
                width = len(max(sc[key]['enum'], key=len))
                self.config_input[i] = ttk.Combobox(
                    tab, width=width,
                    textvariable=self.config_input_var[i],
                    values=sc[key]['enum'])
                self.config_input[i].bind("<<ComboboxSelected>>",
                        lambda event, keyx=key, ix=i:
                            self.set_config_enum(event, keyx, ix))
                self.config_input[i].grid(row=i, column=2, rowspan=1)

            CreateToolTip(lab, sc[key]['description'])

        try:
            self.results.destroy()
        except:
            pass

        # Only ESSENTIAL config items are shown on front page with seeding
        sc = self.o.get_configspec(level=opendrift.config.CONFIG_LEVEL_ESSENTIAL)
        self.seed_input = {}
        self.seed_input_var = {}
        self.seed_input_label = {}
        
        # Create a scrollable frame for seed parameters
        self.seed_frame = ttk.LabelFrame(self.seed, text='SEED PARAMETERS', padding=(5, 5))
        self.seed_frame.grid(row=55, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        
        seed_canvas = tk.Canvas(self.seed_frame, highlightthickness=0, height=120, bg='white')
        seed_scrollbar = ttk.Scrollbar(self.seed_frame, orient="vertical", command=seed_canvas.yview)
        seed_inner = ttk.Frame(seed_canvas)
        
        seed_inner.bind(
            "<Configure>",
            lambda e: seed_canvas.configure(scrollregion=seed_canvas.bbox("all"))
        )
        
        seed_canvas.create_window((0, 0), window=seed_inner, anchor="nw")
        seed_canvas.configure(yscrollcommand=seed_scrollbar.set)
        
        seed_canvas.pack(side="left", fill="both", expand=True)
        seed_scrollbar.pack(side="right", fill="y")
        
        # FIND
        for num, i in enumerate(sc):
            varlabel = i.split(':')[-1]
            if i in self.o.ElementType.variables.keys():
                if 'units' in self.o.ElementType.variables[i].keys():
                    units = self.o.ElementType.variables[i]['units']
                    if units == '1':
                        units = 'fraction'
                    varlabel = '%s [%s]' % (varlabel, units)

            self.seed_input_label[i] = ttk.Label(seed_inner, text=varlabel + '\t')
            self.seed_input_label[i].grid(row=num, column=0, sticky='w', padx=5, pady=2)
            CreateToolTip(self.seed_input_label[i], text=sc[i]['description'])
            actual_val = self.o.get_config(i)
            if sc[i]['type'] == 'enum':
                self.seed_input_var[i] = tk.StringVar()
                self.seed_input[i] = ttk.Combobox(
                    seed_inner, width=50,
                    textvariable=self.seed_input_var[i],
                    values=sc[i]['enum'])
                self.seed_input_var[i].set(actual_val)
            elif sc[i]['type'] == 'bool':
                self.seed_input_var[i] = tk.IntVar(value=sc[i]['value'])
                self.seed_input[i] = ttk.Checkbutton(
                    seed_inner, variable=self.seed_input_var[i],
                    text=sc[i]['description'])
            else:
                self.seed_input_var[i] = tk.StringVar()
                max_length = sc[i].get('max_length') or 12
                max_length = np.minimum(max_length, 64)
                self.seed_input[i] = ttk.Entry(
                    seed_inner, textvariable=self.seed_input_var[i],
                    width=max_length, justify=tk.RIGHT)
                self.seed_input[i].insert(0, actual_val)
            self.seed_input[i].grid(row=num, column=1, sticky='w', padx=5, pady=2)

    def set_config_checkbox(self, key, i):
        i = int(i)
        newval = self.config_input_var[i].get()
        if newval == 0:
            print('Setting %s to False' % key)
            self.o.set_config(key, False)
        elif newval == 1:
            print('Setting %s to True' % key)
            self.o.set_config(key, True)

    def set_config_enum(self, event, key, i):
        newval = self.config_input_var[i].get()
        print('Setting ' + key + newval)
        self.o.set_config(key, newval)

    def show_help(self):
        help_url = 'https://opendrift.github.io/gui.html'
        print('Opening help website:\n' + help_url)
        import webbrowser
        webbrowser.open(help_url)
    
    def clear_output(self):
        """Clear the output text box."""
        self.text.configure(state='normal')
        self.text.delete(1.0, tk.END)
        self.text.configure(state='normal')
        print('Output cleared.')
    
    def copy_output(self):
        """Copy output text to clipboard."""
        output_text = self.text.get(1.0, tk.END)
        self.clipboard_clear()
        self.clipboard_append(output_text)
        print('Output copied to clipboard.')
    
    def save_log(self):
        """Save output log to file."""
        from tkinter import filedialog
        from pathlib import Path
        filename = filedialog.asksaveasfilename(
            initialdir=Path.home(),
            defaultextension='.txt',
            filetypes=[('Text files', '*.txt'), ('Log files', '*.log'), ('All files', '*.*')]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.text.get(1.0, tk.END))
                print(f'Log saved to: {filename}')
            except Exception as e:
                print(f'Error saving log: {e}')
    
    def reset_defaults(self):
        """Reset all configuration to defaults."""
        if hasattr(self, 'o'):
            self.set_model(self.modelname, rebuild_gui=True)
            print('Configuration reset to defaults.')
    
    def load_settings(self):
        """Load settings from JSON file."""
        from tkinter import filedialog
        from pathlib import Path
        import json
        filename = filedialog.askopenfilename(
            initialdir=Path.home(),
            filetypes=[('JSON files', '*.json'), ('All files', '*.*')]
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    settings = json.load(f)
                # Switch model if different (rebuilds seed inputs)
                if 'model' in settings and settings['model'] != self.model.get():
                    self.model.set(settings['model'])
                    self.set_model(settings['model'])
                # Start position
                if 'lon' in settings:
                    self.lon.delete(0, tk.END)
                    self.lon.insert(0, settings['lon'])
                if 'lat' in settings:
                    self.lat.delete(0, tk.END)
                    self.lat.insert(0, settings['lat'])
                if 'radius' in settings:
                    self.radius.delete(0, tk.END)
                    self.radius.insert(0, settings['radius'])
                # End position
                if 'elon' in settings:
                    self.elon.delete(0, tk.END)
                    self.elon.insert(0, settings['elon'])
                if 'elat' in settings:
                    self.elat.delete(0, tk.END)
                    self.elat.insert(0, settings['elat'])
                if 'eradius' in settings:
                    self.eradius.delete(0, tk.END)
                    self.eradius.insert(0, settings['eradius'])
                # Start date/time
                if 'start_date' in settings:
                    self.datevar.set(settings['start_date'])
                if 'start_month' in settings:
                    self.monthvar.set(settings['start_month'])
                if 'start_year' in settings:
                    self.yearvar.set(settings['start_year'])
                if 'start_hour' in settings:
                    self.hourvar.set(settings['start_hour'])
                if 'start_minute' in settings:
                    self.minutevar.set(settings['start_minute'])
                # End date/time
                if 'end_date' in settings:
                    self.edatevar.set(settings['end_date'])
                if 'end_month' in settings:
                    self.emonthvar.set(settings['end_month'])
                if 'end_year' in settings:
                    self.eyearvar.set(settings['end_year'])
                if 'end_hour' in settings:
                    self.ehourvar.set(settings['end_hour'])
                if 'end_minute' in settings:
                    self.eminutevar.set(settings['end_minute'])
                # Timezone, duration, direction
                if 'timezone' in settings:
                    self.timezonevar.set(settings['timezone'])
                if 'duration_hours' in settings:
                    self.durationhours.delete(0, tk.END)
                    self.durationhours.insert(0, settings['duration_hours'])
                if 'direction' in settings:
                    self.directionvar.set(settings['direction'])
                # Restore seed parameters (z, m3_per_hour, oil_type, etc.)
                if 'seed_params' in settings and hasattr(self, 'seed_input_var'):
                    for key, val in settings['seed_params'].items():
                        if key in self.seed_input_var:
                            var = self.seed_input_var[key]
                            if isinstance(var, tk.IntVar):
                                var.set(int(val))
                            else:
                                var.set(str(val))
                            # Also update the underlying config
                            try:
                                self.o.set_config(key, val)
                            except Exception:
                                pass
                print(f'Settings loaded from: {filename}')
            except Exception as e:
                print(f'Error loading settings: {e}')
    
    def save_settings(self):
        """Save current settings to JSON file."""
        from tkinter import filedialog
        from pathlib import Path
        import json
        filename = filedialog.asksaveasfilename(
            initialdir=Path.home(),
            defaultextension='.json',
            filetypes=[('JSON files', '*.json'), ('All files', '*.*')]
        )
        if filename:
            try:
                settings = {
                    'model': self.model.get(),
                    'lon': self.lon.get(),
                    'lat': self.lat.get(),
                    'radius': self.radius.get(),
                    'elon': self.elon.get(),
                    'elat': self.elat.get(),
                    'eradius': self.eradius.get(),
                    'duration_hours': self.durationhours.get(),
                    'direction': self.directionvar.get(),
                    'start_date': self.datevar.get(),
                    'start_month': self.monthvar.get(),
                    'start_year': self.yearvar.get(),
                    'start_hour': self.hourvar.get(),
                    'start_minute': self.minutevar.get(),
                    'end_date': self.edatevar.get(),
                    'end_month': self.emonthvar.get(),
                    'end_year': self.eyearvar.get(),
                    'end_hour': self.ehourvar.get(),
                    'end_minute': self.eminutevar.get(),
                    'timezone': self.timezonevar.get(),
                }
                # Save all seed parameters (z, m3_per_hour, oil_type, etc.)
                if hasattr(self, 'seed_input_var'):
                    seed_params = {}
                    for key, var in self.seed_input_var.items():
                        seed_params[key] = var.get()
                    settings['seed_params'] = seed_params
                with open(filename, 'w') as f:
                    json.dump(settings, f, indent=2)
                print(f'Settings saved to: {filename}')
            except Exception as e:
                print(f'Error saving settings: {e}')

    def convert_lonlat(self):
        convert_url = 'https://www.rapidtables.com/convert/number/degrees-minutes-seconds-to-degrees.html'
        print('Opening conversion website:\n' + convert_url)
        import webbrowser
        webbrowser.open(convert_url)

    def check_seeding(self):
        print('#'*50)
        print('Hang on, plot is comming in a few seconds...')
        print('#'*50)
        month = int(self.months.index(self.monthvar.get()) + 1)
        start_time = datetime(int(self.yearvar.get()), month,
                              int(self.datevar.get()),
                              int(self.hourvar.get()),
                              int(self.minutevar.get()))
        emonth = int(self.months.index(self.emonthvar.get()) + 1)
        end_time = datetime(int(self.eyearvar.get()), emonth,
                            int(self.edatevar.get()),
                            int(self.ehourvar.get()),
                            int(self.eminutevar.get()))
        sys.stdout.flush()
        lon = float(self.lon.get())
        lat = float(self.lat.get())
        radius = float(self.radius.get())
        elon = float(self.elon.get())
        elat = float(self.elat.get())
        eradius = float(self.eradius.get())
        if lon != elon or lat != elat or start_time != end_time:
            lon = [lon, elon]
            lat = [lat, elat]
            radius = [radius, eradius]
            start_time = [start_time, end_time]
            cone = True
        else:
            cone = False

        so = OceanDrift(loglevel=50)
        for k,v in self.GUI_config.items():
            try:
                so.set_config(k, v)
            except:
                pass
        number = self.GUI_config['seed:number']['default']
        if cone is True:
            so.seed_cone(lon=lon, lat=lat, number=number, radius=radius, time=start_time)
        else:
            so.seed_elements(lon=lon, lat=lat, radius=radius, number=number, time=start_time)
        so.plot(buffer=.5, fast=True)
        del so

    def run_opendrift(self):
        # Set button to red while running
        self.start_btn.config(bg='#d32f2f', fg='black',
                              text='RUNNING...', state=tk.DISABLED)
        self.update_idletasks()
        sys.stdout.write('running OpenDrift')

        try:
            self.budgetbutton.destroy()
        except Exception as e:
            #print(e)
            pass
        month = int(self.months.index(self.monthvar.get()) + 1)
        start_time = datetime(int(self.yearvar.get()), month,
                              int(self.datevar.get()),
                              int(self.hourvar.get()),
                              int(self.minutevar.get()))
        emonth = int(self.months.index(self.emonthvar.get()) + 1)
        end_time = datetime(int(self.eyearvar.get()), emonth,
                            int(self.edatevar.get()),
                            int(self.ehourvar.get()),
                            int(self.eminutevar.get()))

        timezone = self.timezonevar.get()
        if timezone != 'UTC':
            import pytz
            local = pytz.timezone(timezone)
            local_start = local.localize(start_time, is_dst=None)
            local_end = local.localize(end_time, is_dst=None)
            start_time = local_start.astimezone(pytz.utc).replace(tzinfo=None)
            end_time = local_end.astimezone(pytz.utc).replace(tzinfo=None)

        # Creating fresh instance of the current model, but keeping config
        adjusted_config = self.o._config
        if self.has_diana is True:
            logfile = self.outputdir + '/opendrift_' + self.modelname + start_time.strftime('_%Y%m%d_%H%M.log')
        else:
            logfile = None
        self.set_model(self.modelname, rebuild_gui=False, logfile=logfile)
        self.o._config = adjusted_config

        sys.stdout.flush()
        lon = float(self.lon.get())
        lat = float(self.lat.get())
        radius = float(self.radius.get())
        elon = float(self.elon.get())
        elat = float(self.elat.get())
        eradius = float(self.eradius.get())
        if lon != elon or lat != elat or start_time != end_time:
            lon = [lon, elon]
            lat = [lat, elat]
            radius = [radius, eradius]
            start_time = [start_time, end_time]
            cone = True
        else:
            cone = False

        for se in self.seed_input:
            val = self.seed_input_var[se].get()
            if self.o._config[se]['type'] in ['float', 'int']:
                val = float(val)
            elif self.o._config[se]['type'] == 'bool':
                if val == 1:
                    val = True
                elif val == 0:
                    val = False
                else:
                    pass
            self.o.set_config(se, val)

        self.o.add_readers_from_list(self.forcing_files)

        self.o.seed_cone(lon=lon, lat=lat, radius=radius,
                         time=start_time)#, #cone=cone,
                         #**extra_seed_args)

        time_step = self.o.get_config('general:time_step_minutes')*60
        time_step_output = self.o.get_config('general:time_step_output_minutes')*60
        duration = int(self.durationhours.get())*3600/time_step
        extra_args = {'time_step': time_step, 'time_step_output': time_step_output}
        if self.directionvar.get() == 'backwards':
            extra_args['time_step'] = -extra_args['time_step']
            extra_args['time_step_output'] = -extra_args['time_step_output']
        if self.has_diana is True:
            extra_args['outfile'] = self.outputdir + '/opendrift_' + \
                self.model.get() + self.o.start_time.strftime('_%Y%m%d_%H%M.nc')

        self.simulationname = 'opendrift_' + self.model.get() + \
            self.o.start_time.strftime('_%Y%m%d_%H%M')

        # Starting simulation run
        try:
            self.o.run(steps=duration, **extra_args)
            logging.getLogger('opendrift').info(self.o)

            # Print clear summary of data sources actually used
            print('\n' + '='*50)
            print('DATA SOURCES USED IN THIS SIMULATION:')
            print('='*50)
            try:
                variable_groups, reader_groups, missing = self.o.env.get_reader_groups()
                used_readers = []
                for rg in reader_groups:
                    for r in rg:
                        if r not in used_readers and r != 'global_landmask':
                            used_readers.append(r)
                if used_readers:
                    for i, r in enumerate(used_readers, 1):
                        print(f'  {i}) {r}')
                else:
                    print('  (no external readers used)')
                print('-'*50)
                print(f'Simulation period: {self.o.start_time} to {self.o.time} UTC')
                print(f'Elements: {self.o.num_elements_active()} active, '
                      f'{self.o.num_elements_deactivated()} deactivated')
                print('='*50 + '\n')
            except Exception:
                pass

        except ValueError as e:
            error_msg = str(e)
            logging.error(f'Simulation failed: {error_msg}')
            messagebox.showerror('Simulation Error', 
                                f'The simulation failed:\n\n{error_msg}\n\n'
                                'Please check that you have selected appropriate data sources '
                                'that cover your simulation area and time period.')
            self.start_btn.config(bg='#4CAF50', fg='white', activebackground='#45a049',
                                  text='START', state=tk.NORMAL)
            return
        except Exception as e:
            error_msg = str(e)
            logging.error(f'Unexpected error during simulation: {error_msg}')
            messagebox.showerror('Simulation Error', 
                                f'An unexpected error occurred:\n\n{error_msg}')
            self.start_btn.config(bg='#4CAF50', fg='white', activebackground='#45a049',
                                  text='START', state=tk.NORMAL)
            return

        # Simulation complete - button back to green
        self.start_btn.config(bg='#4CAF50', fg='white', activebackground='#45a049',
                              text='START', state=tk.NORMAL)

        try:
            os.chmod(extra_args['outfile'], 0o666)
        except:
            pass

        # Model-specific post processing
        self.o.gui_postproc()

        # Notify user that simulation is finished
        messagebox.showinfo('Simulation Complete',
                            f'Simulation finished successfully!\n\n'
                            f'{self.simulationname}')


        try:
            self.results.destroy()
        except:
            pass
        self.results = ttk.Frame(self.seed, padding=(5, 5))
        self.results.grid(row=70, column=0, columnspan=2, sticky='ew', padx=5)
        
        # Result buttons: fill horizontally first (4 per row), then wrap vertically
        buttons = [
            ('Show animation', lambda: self.handle_result('showanimation')),
            ('Save animation', lambda: self.handle_result('saveanimation')),
            ('Show plot', lambda: self.handle_result('showplot')),
            ('Save plot', lambda: self.handle_result('saveplot')),
        ]
        if self.model.get() == 'OpenOil':
            buttons.append(('Show oil budget', lambda: self.handle_result('showoilbudget')))
            buttons.append(('Save oil budget', lambda: self.handle_result('saveoilbudget')))
        if self.model.get() == 'RadionuclideDrift':
            buttons.append(('Show animation specie', lambda: self.handle_result('showanimationspecie')))
            buttons.append(('Save animation specie', lambda: self.handle_result('saveanimationspecie')))
            buttons.append(('Animation profile', lambda: self.handle_result('showanimationprofile')))
            buttons.append(('Plot conc', lambda: self.handle_result('plotconc')))

        max_cols = 4
        for i, (text, cmd) in enumerate(buttons):
            r, c = divmod(i, max_cols)
            ttk.Button(self.results, text=text, command=cmd).grid(row=r, column=c, sticky='ew', padx=2, pady=2)
        for c in range(max_cols):
            self.results.columnconfigure(c, weight=1)



        if self.has_diana is True:
            diana_filename = self.dianadir + self.simulationname + '.nc'
            self.o.write_netcdf_density_map(diana_filename)
            
            ttk.Button(self.results, text='Show in Diana',
                       command=lambda: os.system('diana &')).grid(row=2, column=0, padx=2, pady=2)
            ttk.Button(self.results, text='Copy netCDF file',
                       command=lambda: self.handle_result('copy_netcdf')).grid(row=2, column=1, padx=2, pady=2)

            try:
                os.chmod(diana_filename, 0o666)
            except:
                pass

        # Force canvas to update scroll region and scroll to bottom to show results
        self.seed.update_idletasks()
        self.seed_canvas.configure(scrollregion=self.seed_canvas.bbox("all"))
        self.seed_canvas.yview_moveto(1.0)

        # Bind mousewheel to result buttons so seed canvas scrolls when hovering over them
        if hasattr(self, '_on_seed_mousewheel'):
            self.results.bind("<MouseWheel>", self._on_seed_mousewheel)
            for child in self.results.winfo_children():
                child.bind("<MouseWheel>", self._on_seed_mousewheel)

        # Allow setting config for next run
        self.o.mode = Mode.Config

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--forcing', type=str, help='A file with URLs/names of forcing datasets, overriding built-in data_sources.txt')
    parser.add_argument('-t', '--terminal', action='store_true', help='redirect otput to terminal instead of GUI')

    args = parser.parse_args()

    forcing_files_ok = False
    if args.forcing is not None:
        try:
            with open(args.forcing) as fd:
                forcing_files = fd.readlines()
            forcing_files_ok = True
        except:
            print(f'WARNING: Could not read {args.forcing}, using default OpenDrift forcing configuration instead.')
    if forcing_files_ok is False:
        with open(files('opendrift.scripts').joinpath('data_sources.txt')) as fd:
            forcing_files = fd.readlines()

    ## Add any argument to redirect output to terminal instead of GUI window.
    ## TODO: must be a better way to pass arguments to Tkinter?
    if args.terminal is True:
        os.environ['OPENDRIFT_GUI_OUTPUT'] = 'terminal'
    else:
        os.environ['OPENDRIFT_GUI_OUTPUT'] = 'gui'

    OpenDriftGUI(forcing_files=forcing_files).mainloop()


if __name__ == '__main__':
    main()
