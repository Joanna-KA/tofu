import sys
import os
import logging
import numpy as np
import pkg_resources

from argparse import ArgumentParser
from contextlib import contextmanager
from . import reco, config, tifffile, util
import tofu.vis.qt
from PyQt4 import QtGui, QtCore, uic


LOG = logging.getLogger(__name__)


def set_last_dir(path, line_edit, last_dir):
    if os.path.exists(str(path)):
        line_edit.clear()
        line_edit.setText(path)
        last_dir = str(line_edit.text())

    return last_dir


def get_filtered_filenames(path, exts=['.tif', '.edf']):
    result = []

    try:
        for ext in exts:
            result += [os.path.join(path, f) for f in os.listdir(path) if f.endswith(ext)]
    except OSError:
        return []

    return sorted(result)


@contextmanager
def spinning_cursor():
    QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
    yield
    QtGui.QApplication.restoreOverrideCursor()


class CallableHandler(logging.Handler):
    def __init__(self, func):
        logging.Handler.__init__(self)
        self.func = func

    def emit(self, record):
        self.func(self.format(record))


class ApplicationWindow(QtGui.QMainWindow):
    def __init__(self, app, params):
        QtGui.QMainWindow.__init__(self)
        self.params = params
        self.app = app
        ui_file = pkg_resources.resource_filename(__name__, 'gui.ui')
        self.ui = uic.loadUi(ui_file, self)
        self.ui.show()
        self.ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.ui.tab_widget.setCurrentIndex(0)
        self.ui.slice_dock.setVisible(False)
        self.ui.volume_dock.setVisible(False)
        self.ui.axis_view_widget.setVisible(False)
        self.slice_viewer = None
        self.volume_viewer = None
        self.overlap_viewer = tofu.vis.qt.OverlapViewer()
        self.get_values_from_params()

        log_handler = CallableHandler(self.on_log_record)
        log_handler.setLevel(logging.DEBUG)
        log_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
        root_logger = logging.getLogger('')
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers = [log_handler]

        self.ui.input_path_button.setToolTip(self.get_help('general', 'input'))
        self.ui.proj_button.setToolTip(self.get_help('fbp', 'from-projections'))
        self.ui.y_step.setToolTip(self.get_help('reading', 'y-step'))
        self.ui.method_box.setToolTip(self.get_help('tomographic-reconstruction', 'method'))
        self.ui.axis_spin.setToolTip(self.get_help('tomographic-reconstruction', 'axis'))
        self.ui.angle_step.setToolTip(self.get_help('reconstruction', 'angle'))
        self.ui.angle_offset.setToolTip(self.get_help('tomographic-reconstruction', 'offset'))
        self.ui.oversampling.setToolTip(self.get_help('dfi', 'oversampling'))
        self.ui.iterations_sart.setToolTip(self.get_help('sart', 'max-iterations'))
        self.ui.relaxation.setToolTip(self.get_help('sart', 'relaxation-factor'))
        self.ui.output_path_button.setToolTip(self.get_help('general', 'output'))
        self.ui.ffc_box.setToolTip(self.get_help('gui', 'ffc-correction'))
        self.ui.interpolate_button.setToolTip('Interpolate between two sets of flat fields')
        self.ui.darks_path_button.setToolTip(self.get_help('flat-correction', 'darks'))
        self.ui.flats_path_button.setToolTip(self.get_help('flat-correction', 'flats'))
        self.ui.flats2_path_button.setToolTip(self.get_help('flat-correction', 'flats2'))
        self.ui.path_button_0.setToolTip(self.get_help('gui', 'deg0'))
        self.ui.path_button_180.setToolTip(self.get_help('gui', 'deg180'))

        self.ui.input_path_button.clicked.connect(self.on_input_path_clicked)
        self.ui.sino_button.clicked.connect(self.on_sino_button_clicked)
        self.ui.proj_button.clicked.connect(self.on_proj_button_clicked)
        self.ui.region_box.clicked.connect(self.on_region_box_clicked)
        self.ui.method_box.currentIndexChanged.connect(self.change_method)
        self.ui.axis_spin.valueChanged.connect(self.change_axis_spin)
        self.ui.angle_step.valueChanged.connect(self.change_angle_step)
        self.ui.output_path_button.clicked.connect(self.on_output_path_clicked)
        self.ui.ffc_box.clicked.connect(self.on_ffc_box_clicked)
        self.ui.interpolate_button.clicked.connect(self.on_interpolate_button_clicked)
        self.ui.darks_path_button.clicked.connect(self.on_darks_path_clicked)
        self.ui.flats_path_button.clicked.connect(self.on_flats_path_clicked)
        self.ui.flats2_path_button.clicked.connect(self.on_flats2_path_clicked)
        self.ui.ffc_options.currentIndexChanged.connect(self.change_ffc_options)
        self.ui.reco_button.clicked.connect(self.on_reconstruct)
        self.ui.path_button_0.clicked.connect(self.on_path_0_clicked)
        self.ui.path_button_180.clicked.connect(self.on_path_180_clicked)
        self.ui.show_slices_button.clicked.connect(self.on_show_slices_clicked)
        self.ui.show_volume_button.clicked.connect(self.on_show_volume_clicked)
        self.ui.run_button.clicked.connect(self.on_compute_center)
        self.ui.save_action.triggered.connect(self.on_save_as)
        self.ui.clear_action.triggered.connect(self.on_clear)
        self.ui.clear_output_dir_action.triggered.connect(self.on_clear_output_dir_clicked)
        self.ui.open_action.triggered.connect(self.on_open_from)
        self.ui.close_action.triggered.connect(self.close)
        self.ui.extrema_checkbox.clicked.connect(self.on_remove_extrema_clicked)
        self.ui.overlap_opt.currentIndexChanged.connect(self.on_overlap_opt_changed)

        self.ui.input_path_line.textChanged.connect(lambda value: self.change_value('input', str(self.ui.input_path_line.text())))
        self.ui.sino_button.clicked.connect(lambda value: self.change_value('from_projections', False))
        self.ui.proj_button.clicked.connect(lambda value: self.change_value('from_projections', True))
        self.ui.y_step.valueChanged.connect(lambda value: self.change_value('y_step', value))
        self.ui.angle_offset.valueChanged.connect(lambda value: self.change_value('offset', value))
        self.ui.oversampling.valueChanged.connect(lambda value: self.change_value('oversampling', value))
        self.ui.iterations_sart.valueChanged.connect(lambda value: self.change_value('max_iterations', value))
        self.ui.relaxation.valueChanged.connect(lambda value: self.change_value('relaxation_factor', value))
        self.ui.output_path_line.textChanged.connect(lambda value: self.change_value('output', str(self.ui.output_path_line.text())))
        self.ui.darks_path_line.textChanged.connect(lambda value: self.change_value('darks', str(self.ui.darks_path_line.text())))
        self.ui.flats_path_line.textChanged.connect(lambda value: self.change_value('flats', str(self.ui.flats_path_line.text())))
        self.ui.flats2_path_line.textChanged.connect(lambda value: self.change_value('flats2', str(self.ui.flats2_path_line.text())))
        self.ui.fix_naninf_box.clicked.connect(lambda value: self.change_value('fix_nan_and_inf', self.ui.fix_naninf_box.isChecked()))
        self.ui.absorptivity_box.clicked.connect(lambda value: self.change_value('absorptivity', self.ui.absorptivity_box.isChecked()))
        self.ui.path_line_0.textChanged.connect(lambda value: self.change_value('deg0', str(self.ui.path_line_0.text())))
        self.ui.path_line_180.textChanged.connect(lambda value: self.change_value('deg180', str(self.ui.path_line_180.text())))

        self.ui.overlap_layout.addWidget(self.overlap_viewer)
        self.overlap_viewer.slider.valueChanged.connect(self.on_axis_slider_changed)

    def on_log_record(self, record):
        self.ui.text_browser.append(record)

    def get_values_from_params(self):
        self.ui.input_path_line.setText(self.params.input)
        self.ui.output_path_line.setText(self.params.output)
        self.ui.darks_path_line.setText(self.params.darks)
        self.ui.flats_path_line.setText(self.params.flats)
        self.ui.flats2_path_line.setText(self.params.flats2)
        self.ui.path_line_0.setText(self.params.deg0)
        self.ui.path_line_180.setText(self.params.deg180)

        self.ui.y_step.setValue(self.params.y_step if self.params.y_step else 1)
        self.ui.axis_spin.setValue(self.params.axis if self.params.axis else 0.0)
        self.ui.angle_step.setValue(self.params.angle if self.params.angle else 0.0)
        self.ui.angle_offset.setValue(self.params.offset if self.params.offset else 0.0)
        self.ui.oversampling.setValue(self.params.oversampling if self.params.oversampling else 0)
        self.ui.iterations_sart.setValue(self.params.max_iterations if
                                         self.params.max_iterations else 0)
        self.ui.relaxation.setValue(self.params.relaxation_factor if
                                    self.params.relaxation_factor else 0.0)

        if self.params.from_projections:
            self.ui.proj_button.setChecked(True)
            self.ui.sino_button.setChecked(False)
            self.on_proj_button_clicked()
        else:
            self.ui.proj_button.setChecked(False)
            self.ui.sino_button.setChecked(True)
            self.on_sino_button_clicked()

        if self.params.method == "fbp":
            self.ui.method_box.setCurrentIndex(0)
        elif self.params.method == "dfi":
            self.ui.method_box.setCurrentIndex(1)
        elif self.params.method == "sart":
            self.ui.method_box.setCurrentIndex(2)

        self.change_method()

        if self.params.y_step > 1 and self.sino_button.isChecked():
            self.ui.region_box.setChecked(True)
        else:
            self.ui.region_box.setChecked(False)
        self.ui.on_region_box_clicked()

        ffc_enabled = bool(self.params.flats) and bool(self.params.darks) and self.proj_button.isChecked()
        self.ui.ffc_box.setChecked(ffc_enabled)
        self.ui.preprocessing_container.setVisible(ffc_enabled)
        self.ui.interpolate_button.setChecked(bool(self.params.flats2) and ffc_enabled)

        self.ui.fix_naninf_box.setChecked(self.params.fix_nan_and_inf)
        self.ui.absorptivity_box.setChecked(self.params.absorptivity)

        if self.params.reduction_mode.lower() == "average":
            self.ui.ffc_options.setCurrentIndex(0)
        else:
            self.ui.ffc_options.setCurrentIndex(1)

    def change_method(self):
        self.params.method = str(self.ui.method_box.currentText()).lower()
        is_dfi = self.params.method == 'dfi'
        is_sart = self.params.method == 'sart'

        for w in (self.ui.oversampling_label, self.ui.oversampling):
            w.setVisible(is_dfi)

        for w in (self.ui.relaxation, self.ui.relaxation_label,
                  self.ui.iterations_sart, self.ui.iterations_sart_label):
            w.setVisible(is_sart)

    def get_help(self, section, name):
        help = config.SECTIONS[section][name]['help']
        return help

    def change_value(self, name, value):
        setattr(self.params, name, value)

    def on_sino_button_clicked(self):
        self.ffc_box.setEnabled(False)
        self.ui.preprocessing_container.setVisible(False)

    def on_proj_button_clicked(self):
        self.ffc_box.setEnabled(False)
        self.ui.preprocessing_container.setVisible(self.ffc_box.isChecked())

        if self.ui.proj_button.isChecked():
            self.ui.ffc_box.setEnabled(True)
            self.ui.region_box.setEnabled(False)
            self.ui.region_box.setChecked(False)
            self.on_region_box_clicked()

    def on_region_box_clicked(self):
        self.ui.y_step.setEnabled(self.ui.region_box.isChecked())
        if self.ui.region_box.isChecked():
            self.params.y_step = self.ui.y_step.value()
        else:
            self.params.y_step = 1

    def on_input_path_clicked(self, checked):
        path = self.get_path(self.params.input, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.input_path_line, self.params.last_dir)

    def change_axis_spin(self):
        if self.ui.axis_spin.value() == 0:
            self.params.axis = None
        else:
            self.params.axis = self.ui.axis_spin.value()

    def change_angle_step(self):
        if self.ui.angle_step.value() == 0:
            self.params.angle = None
        else:
            self.params.angle = self.ui.angle_step.value()

    def on_output_path_clicked(self, checked):
        path = self.get_path(self.params.output, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.output_path_line, self.params.last_dir)
        self.new_output = True

    def on_clear_output_dir_clicked(self):
        with spinning_cursor():
            output_absfiles = get_filtered_filenames(str(self.ui.output_path_line.text()))

            for f in output_absfiles:
                os.remove(f)

    def on_ffc_box_clicked(self):
        checked = self.ui.ffc_box.isChecked()
        self.ui.preprocessing_container.setVisible(checked)
        self.params.ffc_correction = checked

    def on_interpolate_button_clicked(self):
        checked = self.ui.interpolate_button.isChecked()
        self.ui.flats2_path_line.setEnabled(checked)
        self.ui.flats2_path_button.setEnabled(checked)

    def change_ffc_options(self):
        self.params.reduction_mode = str(self.ui.ffc_options.currentText()).lower()

    def on_darks_path_clicked(self, checked):
        path = self.get_path(self.params.darks, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.darks_path_line, self.params.last_dir)

    def on_flats_path_clicked(self, checked):
        path = self.get_path(self.params.flats, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.flats_path_line, self.params.last_dir)

    def on_flats2_path_clicked(self, checked):
        path = self.get_path(self.params.flats2, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.flats2_path_line, self.params.last_dir)

    def get_path(self, directory, last_dir):
        return QtGui.QFileDialog.getExistingDirectory(self, '.', last_dir or directory)

    def get_filename(self, directory, last_dir):
        return QtGui.QFileDialog.getOpenFileName(self, '.', last_dir or directory)

    def on_path_0_clicked(self, checked):
        path = self.get_filename(self.params.deg0, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.path_line_0, self.params.last_dir)

    def on_path_180_clicked(self, checked):
        path = self.get_filename(self.params.deg180, self.params.last_dir)
        self.params.last_dir = set_last_dir(path, self.ui.path_line_180, self.params.last_dir)

    def on_open_from(self):
        config_file = QtGui.QFileDialog.getOpenFileName(self, 'Open ...', self.params.last_dir)
        parser = ArgumentParser()
        params = config.TomoParams(sections=('gui',))
        parser = params.add_arguments(parser)
        self.params = parser.parse_known_args(config.config_to_list(config_name=config_file))[0]
        self.get_values_from_params()

    def on_save_as(self):
        if os.path.exists(self.params.last_dir):
            config_file = str(self.params.last_dir + "/reco.conf")
        else:
            config_file = str(os.getenv('HOME') + "reco.conf")
        save_config = QtGui.QFileDialog.getSaveFileName(self, 'Save as ...', config_file)
        if save_config:
            sections = config.TomoParams().sections + ('gui',)
            config.write(save_config, args=self.params, sections=sections)

    def on_clear(self):
        self.ui.axis_view_widget.setVisible(False)

        self.ui.input_path_line.setText('.')
        self.ui.output_path_line.setText('.')
        self.ui.darks_path_line.setText('.')
        self.ui.flats_path_line.setText('.')
        self.ui.flats2_path_line.setText('.')
        self.ui.path_line_0.setText('.')
        self.ui.path_line_180.setText('.')

        self.ui.fix_naninf_box.setChecked(True)
        self.ui.absorptivity_box.setChecked(True)
        self.ui.sino_button.setChecked(True)
        self.ui.proj_button.setChecked(False)
        self.ui.region_box.setChecked(False)
        self.ui.ffc_box.setChecked(False)
        self.ui.interpolate_button.setChecked(False)

        self.ui.y_step.setValue(1)
        self.ui.axis_spin.setValue(0)
        self.ui.angle_step.setValue(0)
        self.ui.angle_offset.setValue(0)
        self.ui.oversampling.setValue(0)
        self.ui.ffc_options.setCurrentIndex(0)

        self.ui.text_browser.clear()
        self.ui.method_box.setCurrentIndex(0)

        self.params.from_projections = False
        self.params.enable_cropping = False
        self.params.reduction_mode = "average"
        self.params.fix_nan_and_inf = True
        self.params.absorptivity = True
        self.params.show_2d = False
        self.params.show_3d = False
        self.params.angle = None
        self.params.axis = None
        self.on_region_box_clicked()
        self.on_ffc_box_clicked()
        self.on_interpolate_button_clicked()

    def closeEvent(self, event):
        try:
            sections = config.TomoParams().sections + ('gui',)
            config.write('reco.conf', args=self.params, sections=sections)
        except IOError as e:
            self.gui_warn(str(e))
            self.on_save_as()

    def on_reconstruct(self):
        with spinning_cursor():
            self.ui.centralWidget.setEnabled(False)
            self.repaint()
            self.app.processEvents()

            input_images = get_filtered_filenames(str(self.ui.input_path_line.text()))

            if not input_images:
                self.gui_warn("No data found in {}".format(str(self.ui.input_path_line.text())))
                self.ui.centralWidget.setEnabled(True)
                return

            im = util.read_image(input_images[0])
            self.params.width = im.shape[1]
            self.params.height = im.shape[0]
            self.params.ffc_correction = self.params.ffc_correction and self.ui.proj_button.isChecked()

            if self.params.y_step > 1:
                self.params.angle *= self.params.y_step

            if self.params.ffc_correction:
                flats_files = get_filtered_filenames(str(self.ui.flats_path_line.text()))
                self.params.num_flats = len(flats_files)
            else:
                self.params.num_flats = 0
                self.params.darks = None
                self.params.flats = None

            self.params.flats2 = self.ui.flats2_path_line.text() if self.ui.interpolate_button.isChecked() else ''
            self.params.oversampling = self.ui.oversampling.value() if self.params.method == 'dfi' else None

            if self.params.method == 'sart':
                self.params.num_angles = len(input_images) if self.params.from_projections else self.params.height
                self.params.max_iterations = self.ui.iterations_sart.value()
                self.params.relaxation_factor = self.ui.relaxation.value()

                if self.params.angle is None:
                    self.gui_warn("Missing argument for Angle step (rad)")
            else:
                try:
                    reco.tomo(self.params)
                except Exception as e:
                    self.gui_warn(str(e))

            self.ui.centralWidget.setEnabled(True)
            self.params.angle = self.ui.angle_step.value()

    def on_show_slices_clicked(self):
        path = str(self.ui.output_path_line.text())
        filenames = get_filtered_filenames(path)

        if not self.slice_viewer:
            self.slice_viewer = tofu.vis.qt.ImageViewer(filenames)
            self.slice_dock.setWidget(self.slice_viewer)
            self.ui.slice_dock.setVisible(True)
        else:
            self.slice_viewer.load_files(filenames)

    def on_show_volume_clicked(self):
        if not self.volume_viewer:
            step = int(self.ui.reduction_box.currentText())
            self.volume_viewer = tofu.vis.qt.VolumeViewer(parent=self, step=step)
            self.volume_dock.setWidget(self.volume_viewer)
            self.ui.volume_dock.setVisible(True)

        path = str(self.ui.output_path_line.text())
        filenames = get_filtered_filenames(path)
        self.volume_viewer.load_files(filenames)

    def on_compute_center(self):
        first_name = str(self.ui.path_line_0.text())
        second_name = str(self.ui.path_line_180.text())
        first = tifffile.TiffFile(first_name).asarray().astype(np.float)
        second = tifffile.TiffFile(second_name).asarray().astype(np.float)

        self.axis = reco.compute_rotation_axis(first, second)
        self.height, self.width = first.shape

        w2 = self.width / 2.0
        position = w2 + (w2 - self.axis) * 2.0
        self.overlap_viewer.set_images(first, second)
        self.overlap_viewer.set_position(position)
        self.ui.img_size.setText('width = {} | height = {}'.format(self.width, self.height))

    def on_remove_extrema_clicked(self, val):
        self.ui.overlap_viewer.remove_extrema = val

    def on_overlap_opt_changed(self, index):
        self.ui.overlap_viewer.subtract = index == 0
        self.ui.overlap_viewer.update_image()

    def on_axis_slider_changed(self):
        val = self.overlap_viewer.slider.value()
        w2 = self.width / 2.0
        self.axis = w2 + (w2 - val) / 2
        self.ui.axis_num.setText('{} px'.format(self.axis))
        self.ui.axis_spin.setValue(self.axis)

    def gui_warn(self, message):
        QtGui.QMessageBox.warning(self, "Warning", message)


def main(params):
    app = QtGui.QApplication(sys.argv)
    ApplicationWindow(app, params)
    sys.exit(app.exec_())
