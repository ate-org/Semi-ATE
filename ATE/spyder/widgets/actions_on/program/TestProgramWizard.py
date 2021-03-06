from ATE.spyder.widgets.actions_on.program.Binning.BinningHandler import BinningHandler
import os
import re

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QTreeWidgetItem, QTreeWidgetItemIterator
from ATE.spyder.widgets.actions_on.program.Parameters.OutputParameter import OutputParameter

from ATE.spyder.widgets.actions_on.program.Binning.BinTableGenerator import BinTableGenerator
from ATE.spyder.widgets.actions_on.utils.BaseDialog import BaseDialog
from ATE.spyder.widgets.actions_on.program.Utils import (BINGROUPS, ParameterEditability, ResolverTypes, Action, Sequencer, Result,
                                                         BinningColumns, ErrorMessage, ParameterState, InputFieldsPosition, OutputFieldsPosition, GRADES)
from ATE.spyder.widgets.actions_on.program.Parameters.TestProgram import (TestProgram, TestParameters)
from ATE.spyder.widgets.navigation import ProjectNavigation
from ATE.spyder.widgets.actions_on.utils.FileSystemOperator import FileSystemOperator


DEFAULT_TEMPERATURE = '25'
MAX_SBIN_NUM = 65535
ORANGE = (255, 127, 39)
RED = (237, 28, 36)
GREEN = (34, 117, 76)
ORANGE_LABEL = 'color: orange'


class TestProgramWizard(BaseDialog):
    def __init__(self, project_info: ProjectNavigation, owner: str, parent=None, read_only: bool = False, enable_edit: bool = True, prog_name: str = ''):
        super().__init__(__file__, project_info.parent)
        self.project_info = project_info
        self.owner = owner

        self.available_tests = []
        self.read_only = read_only
        self.enable_edit = enable_edit
        self.prog_name = prog_name

        self.current_selected_test = None
        self.result = None
        self._is_dynamic_range_valid = True
        self.bin_counter = 10
        self.cell_size = 0
        self._standard_parameter_handler = TestProgram()
        self._custom_parameter_handler = TestProgram()
        self._bin_table = BinTableGenerator()
        self.binning_table: QTableWidget = self.binning_table
        self._available_gp_functions = self.project_info.get_hardware_definition(self.project_info.active_hardware)["GPFunctions"]
        self._binning_handler = BinningHandler(self.binning_table, self._bin_table, self)

        self._setup()
        self._view()
        self._connect_event_handler()

        # TODO: hack to simplify the devloper's life
        # so that each output can be automaticaly asigned to a soft-bin
        if self.binning_table.rowCount() == 0:
            self._add_new_bin()

    def _setup(self):
        self._set_icon(self.testAdd, 'arrow-right')
        self._set_icon(self.testRemove, 'arrow-left')
        self._set_icon(self.moveTestDown, 'arrow-down')
        self._set_icon(self.moveTestUp, 'arrow-up')

        self._resize_table(self.parametersInput, 50)
        self._resize_table(self.parametersOutput, 50)

        from ATE.spyder.widgets.validation import valid_float_regex
        regx = QtCore.QRegExp(valid_float_regex)
        self.positive_float_validator = QtGui.QRegExpValidator(regx, self)

        from ATE.spyder.widgets.validation import valid_integer_regex
        regx = QtCore.QRegExp(valid_integer_regex)
        integer_validator = QtGui.QRegExpValidator(regx, self)
        self.temperature.setValidator(integer_validator)

    def _connect_event_handler(self):
        self.selectedTests.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.selectedTests.horizontalHeader().setStretchLastSection(True)
        self.selectedTests.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.selectedTests.itemDoubleClicked.connect(self._double_click_handler)
        self.selectedTests.itemClicked.connect(self._test_selected)
        self.selectedTests.itemSelectionChanged.connect(self._table_clicked)
        self.selectedTests.setSelectionBehavior(QtWidgets.QTableView.SelectRows)

        self.binning_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.binning_tree.customContextMenuRequested.connect(self._context_menu_binning_tree)
        self.binning_tree.itemClicked.connect(self._binning_tree_clicked)
        self.binning_tree.setItemsExpandable(False)
        self.binning_tree.clear()

        self.binning_table.itemDoubleClicked.connect(self._binning_table_item_double_clicked)
        self.binning_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.binning_table.customContextMenuRequested.connect(self._context_menu_binning_table)
        self.binning_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.binning_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        self.availableTests.itemClicked.connect(self._available_test_selected)
        self.availableTests.itemSelectionChanged.connect(self._available_table_clicked)

        self.parametersInput.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.parametersInput.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.parametersInput.horizontalHeader().setSectionResizeMode(InputFieldsPosition.Value(), QtWidgets.QHeaderView.ResizeToContents)
        self.parametersInput.customContextMenuRequested.connect(self._context_menu_input_params)
        self.parametersInput.itemDoubleClicked.connect(self._double_click_handler_input_param)
        self.parametersOutput.itemDoubleClicked.connect(self._double_click_handler_output_param)
        self.parametersInput.itemClicked.connect(self._input_param_table_clicked)
        self.parametersOutput.itemClicked.connect(self._output_param_table_clicked)

        self.testAdd.clicked.connect(lambda: self._move_test(Action.Right()))
        self.moveTestDown.clicked.connect(lambda: self._move_test(Action.Down()))
        self.moveTestUp.clicked.connect(lambda: self._move_test(Action.Up()))
        self.testRemove.clicked.connect(lambda: self._move_test(Action.Left()))

        self.hardware.currentIndexChanged.connect(self._hardware_changed)
        self.base.currentIndexChanged.connect(self._base_changed)
        self.usertext.textChanged.connect(self._usertext_changed)
        self.target.currentIndexChanged.connect(self._target_changed)

        self.sequencerType.currentIndexChanged.connect(self._sequencer_type_changed)
        self.temperature.textChanged.connect(self._verify_temperature)
        from ATE.spyder.widgets.validation import valid_user_text_name_regex
        user_text_reg_ex = QtCore.QRegExp(valid_user_text_name_regex)
        user_text_name_validator = QtGui.QRegExpValidator(user_text_reg_ex, self)
        self.usertext.setValidator(user_text_name_validator)

        self.OKButton.clicked.connect(self._save_configuration)
        self.CancelButton.clicked.connect(self._cancel)

        self.remove_bin.clicked.connect(self._remove_selected_bin)
        self.add_bin.clicked.connect(self._add_new_bin)
        self.import_bin_table.clicked.connect(self._import_bin_table)

    def _view(self):
        self.existing_hardwares = self.project_info.get_active_hardware_names()
        self.hardware.addItems(self.existing_hardwares)
        current_hw_index = self.hardware.findText(self.project_info.active_hardware, QtCore.Qt.MatchExactly)
        self.hardware.setCurrentIndex(current_hw_index)

        self.hardware.setEnabled(False)
        self.target.setEnabled(False)
        self.base.setEnabled(False)

        self.cacheType.addItems(self._available_gp_functions)
        if len(self._available_gp_functions) == 0:
            self.cacheDrop.setChecked(False)
            self.cacheDrop.setEnabled(False)
            self.cacheStore.setChecked(False)
            self.cacheStore.setEnabled(False)
            self.cacheDisable.setChecked(True)
            self.cacheDisable.setEnabled(False)

        current_base_index = self.base.findText(self.project_info.active_base, QtCore.Qt.MatchExactly)
        self.base.setCurrentIndex(current_base_index)

        self._update_target()

        self.sequencerType.addItems([Sequencer.Static(), Sequencer.Dynamic()])
        self.temperature.setText(DEFAULT_TEMPERATURE)

        self._update_test_list()
        self.Feedback.setText('')
        self.Feedback.setStyleSheet(ORANGE_LABEL)
        self.usertext_feedback.setStyleSheet(ORANGE_LABEL)
        self.temperature_feedback.setStyleSheet(ORANGE_LABEL)
        self.target_feedback.setStyleSheet(ORANGE_LABEL)
        self.usertext_feedback.setStyleSheet(ORANGE_LABEL)

        if not self.prog_name:
            owner, count = self._get_test_program_infos()
            self.prog_name = self._generate_test_program_name(owner, count)

        base_name = ' '.join(re.findall('.[^A-Z]*', os.path.basename(__file__).replace('.py', '')))
        self.setWindowTitle(f"{base_name} :{self.prog_name}")

        self._verify()

    @QtCore.pyqtSlot(QtCore.QPoint)
    def _context_menu_binning_tree(self, point: QtCore.QPoint):
        item = self.binning_tree.itemAt(point)
        self.binning_tree.clearSelection()

        if not item or item.childCount():
            return

        if not self._is_output_valid(item.text(0)):
            return

        elements = self._bin_table.get_available_bin_names()
        if not elements:
            return

        menu = self._generate_menu(elements)
        action = menu.exec_(self.binning_tree.mapToGlobal(point))

        if action is None:
            return None

        bin_name = action.text()

        # hack we cannot restore the default theme color after changing it
        # so we generate a new tree item
        output = self._custom_parameter_handler.get_output_parameter_from_test_instance(item.text(0))
        if not output.is_bin_parameter_valid():
            self._update_bin_tree_element(item, bin_name)
        else:
            item.setText(1, bin_name)

        output.set_bin_name(bin_name)
        self._verify()

    def _is_output_valid(self, test_instance_name: str) -> bool:
        output = self._custom_parameter_handler.get_output_parameter_from_test_instance(test_instance_name)
        if not output:
            return False

        return output.is_valid()

    def _update_bin_tree_element(self, item, text):
        self.binning_tree.blockSignals(True)
        parent = item.parent()
        index = parent.indexOfChild(item)
        new_item = QTreeWidgetItem()
        new_item.setText(0, item.text(0))
        new_item.setText(1, text)
        parent.removeChild(item)
        parent.insertChild(index, new_item)
        self.binning_tree.blockSignals(False)

    @QtCore.pyqtSlot(QtCore.QPoint)
    def _context_menu_binning_table(self, point):
        self._binning_handler.context_menu_handler(point)

    def _generate_menu(self, elements: list):
        menu = QtWidgets.QMenu(self.project_info.parent)
        for action in elements:
            menu.addAction(action)

        return menu

    @QtCore.pyqtSlot(QTreeWidgetItem)
    def _binning_tree_clicked(self, _):
        self.binning_tree.clearSelection()

    @staticmethod
    def _get_sbin(text):
        for elem in GRADES:
            if elem[0] == text:
                return str(elem[1])

        return text

    def _table_clicked(self):
        if len(self.selectedTests.selectedItems()):
            return

    def _double_click_handler(self, item):
        if item.column() == 0:
            return

        from ATE.spyder.widgets.validation import valid_test_name_description_regex
        regx = QtCore.QRegExp(valid_test_name_description_regex)
        name_validator = QtGui.QRegExpValidator(regx, self)

        self._create_checkable_cell(item.text(), self.selectedTests, item, name_validator)

    @QtCore.pyqtSlot(QtWidgets.QTableWidgetItem)
    def _input_param_table_clicked(self, item):
        if item.column() in (InputFieldsPosition.Name(), InputFieldsPosition.Min(), InputFieldsPosition.Max,
                             InputFieldsPosition.Unit(), InputFieldsPosition.Format()) or self.read_only:
            return

        self._verify()

    @QtCore.pyqtSlot(QtWidgets.QTableWidgetItem)
    def _output_param_table_clicked(self, item):
        if item.column() in (OutputFieldsPosition.Name(), OutputFieldsPosition.Lsl(), OutputFieldsPosition.Usl(),
                             OutputFieldsPosition.Unit(), OutputFieldsPosition.Format()) or self.read_only:
            return

        self._verify()

    @staticmethod
    def _set_icon(button, icon_type):
        from ATE.spyder.widgets.actions_on.program.Actions import ACTIONS
        icon = QtGui.QIcon(ACTIONS[icon_type][0])
        button.setIcon(icon)
        button.setText("")

    @staticmethod
    def _resize_table(table, col_size):
        for c in range(table.columnCount()):
            table.setColumnWidth(c, col_size)

        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(InputFieldsPosition.Type(), QtWidgets.QHeaderView.Stretch)
        table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

    def _update_target(self):
        self.target.blockSignals(True)
        self.target.clear()
        if self.base.currentText() == 'PR':
            existing_targets = self.project_info.get_active_die_names_for_hardware(self.hardware.currentText())
        else:
            existing_targets = self.project_info.get_active_device_names_for_hardware(self.hardware.currentText())

        self.target.addItems(existing_targets)
        current_target_index = self.target.findText(self.project_info.active_target, QtCore.Qt.MatchExactly)
        # If we cannot find the active target, we just use the first
        # available target.
        if (current_target_index < 0):
            current_target_index = 0
        self.target.setCurrentIndex(current_target_index)
        self.target.blockSignals(False)

    @QtCore.pyqtSlot(str)
    def _usertext_changed(self, text):
        self._verify()

    @QtCore.pyqtSlot()
    def _hardware_changed(self):
        self._update_target()
        self._verify()

    @QtCore.pyqtSlot()
    def _base_changed(self):
        self._update_target()
        self._verify()

    @QtCore.pyqtSlot()
    def _target_changed(self):
        self._verify()

    @QtCore.pyqtSlot(int)
    def _sequencer_type_changed(self, index):
        if self.sequencerType.itemText(index) == Sequencer.Static():
            from ATE.spyder.widgets.validation import valid_integer_regex
            regx = QtCore.QRegExp(valid_integer_regex)
            integer_validator = QtGui.QRegExpValidator(regx, self)
            self.temperature.setValidator(integer_validator)
            self.temperature.setText(DEFAULT_TEMPERATURE)
            return

        from ATE.spyder.widgets.validation import valid_temp_sequence_regex
        regx = QtCore.QRegExp(valid_temp_sequence_regex)
        integer_validator = QtGui.QRegExpValidator(regx, self)
        self.temperature.setValidator(integer_validator)

        self.temperature.setText(f'{DEFAULT_TEMPERATURE},')

    @QtCore.pyqtSlot(QtWidgets.QListWidgetItem)
    def _available_test_selected(self, item):
        self.parametersInput.setEnabled(False)
        self.parametersOutput.setEnabled(False)

        self.selectedTests.blockSignals(True)
        self.selectedTests.clearSelection()
        self.selectedTests.blockSignals(False)

        self._display_active_test()

    @QtCore.pyqtSlot()
    def _available_table_clicked(self):
        self.parametersInput.setEnabled(False)
        self.parametersOutput.setEnabled(False)
        self.parametersInput.setRowCount(0)
        self.parametersOutput.setRowCount(0)

    @QtCore.pyqtSlot(QtWidgets.QTableWidgetItem)
    def _test_selected(self, item):
        self.selectedTests.blockSignals(True)
        if not self.read_only:
            self.parametersInput.setEnabled(True)
            self.parametersOutput.setEnabled(True)

        self.availableTests.blockSignals(True)
        self.availableTests.clearSelection()
        self.availableTests.blockSignals(False)

        row = item.row()
        self.selectedTests.item(row, 0).setSelected(True)
        self.selectedTests.item(row, 1).setSelected(True)

        test_name = self.selectedTests.item(row, 1).text()
        self._custom_parameter_handler.display_test(test_name, self.parametersInput, self.parametersOutput)
        self.selectedTests.blockSignals(False)

    def _validate_test_parameters(self, test_name):
        self._custom_parameter_handler.validate_test_parameters(test_name, self._standard_parameter_handler)

    @staticmethod
    def _extract_base_test_name(indexed_test_name):
        return indexed_test_name.split('_')[0]

    def _get_in_output_paramters(self, test_name):
        name = self._extract_base_test_name(test_name)
        self.current_selected_test = name
        parameters = self._get_test_parameters(name)

        return parameters['input_parameters'], parameters['output_parameters']

    # ToDo: Improve Exception handling, as all exceptions
    #       thrown in handlers will be discarded and replaced
    #       by "action not recognized"
    @QtCore.pyqtSlot(str)
    def _move_test(self, action):
        try:
            {Action.Up(): lambda: self._move_up(),
             Action.Down(): lambda: self._move_down(),
             Action.Left(): lambda: self._remove_from_testprogram(),
             Action.Right(): lambda: self._add_to_testprogram(),
             }[action]()
        except KeyError:
            raise f"action '{action}' not recognized"
        except Exception as e:
            raise e

        self._verify()

    @staticmethod
    def _is_test_selected(test_list):
        selected_items = len(test_list.selectedItems())
        if not selected_items:
            return False
        return True

    @QtCore.pyqtSlot()
    def _move_up(self):
        self.selectedTests.blockSignals(True)
        selected = self.selectedTests.selectedItems()
        if not len(selected):
            self._update_feedback(ErrorMessage.NotSelected())
            return

        row = selected[0].row()
        if row == 0:
            pass
        else:
            test_name = self.selectedTests.item(row, 1).text()
            self._custom_parameter_handler.reorder_test(test_name, Action.Up())
            self._switch_item_names(row, row - 1)

        self.selectedTests.selectRow(row - 1)
        self.selectedTests.blockSignals(False)

    @QtCore.pyqtSlot()
    def _move_down(self):
        self.selectedTests.blockSignals(True)
        selected = self.selectedTests.selectedItems()
        row = selected[0].row()
        if not len(selected) or row == self.selectedTests.rowCount() - 1:
            self._update_feedback(ErrorMessage.NotSelected())
        else:
            test_name = self.selectedTests.item(row, 1).text()
            self._custom_parameter_handler.reorder_test(test_name, Action.Down())
            self._switch_item_names(row, row + 1)

        self.selectedTests.blockSignals(False)
        self.selectedTests.selectRow(row + 1)

    def _switch_item_names(self, row, next_row):
        item_base = self.selectedTests.takeItem(row, 0)
        item_instance = self.selectedTests.takeItem(row, 1)

        switch_item_base = self.selectedTests.takeItem(next_row, 0)
        switch_item_instance = self.selectedTests.takeItem(next_row, 1)

        self.selectedTests.setItem(row, 0, switch_item_base)
        self.selectedTests.setItem(row, 1, switch_item_instance)

        self.selectedTests.setItem(next_row, 0, item_base)
        self.selectedTests.setItem(next_row, 1, item_instance)

    @QtCore.pyqtSlot()
    def _remove_from_testprogram(self):
        self.selectedTests.blockSignals(True)
        if not self._is_test_selected(self.selectedTests):
            self._update_feedback(ErrorMessage.NotSelected())
            return

        self.parametersInput.setRowCount(0)
        self.parametersOutput.setRowCount(0)

        item = self.selectedTests.selectedItems()[0]
        row = item.row()
        test_name = self.selectedTests.item(row, 1).text()
        self._custom_parameter_handler.remove_test(test_name)
        self.selectedTests.removeRow(row)
        self._populate_binning_tree()

        self.selectedTests.blockSignals(False)

    @QtCore.pyqtSlot()
    def _add_to_testprogram(self):
        self.availableTests.blockSignals(True)
        if not self._is_test_selected(self.availableTests):
            self._update_feedback(ErrorMessage.NotSelected())
            return

        for item in self.availableTests.selectedItems():
            self._add_test_tuple_items(item.text())
        self.availableTests.blockSignals(False)

    @QtCore.pyqtSlot(str)
    def _verify_temperature(self, text):
        self.parametersInput.setRowCount(0)
        self.parametersOutput.setRowCount(0)

        self.availableTests.clearSelection()
        self.selectedTests.clearSelection()

        if not text:
            self.temperature_feedback.setText(ErrorMessage.TemperatureMissed())
        else:
            temps = []
            if self.sequencer_type == Sequencer.Static():
                temps = [text]
                if not len(self.temperature.text()):
                    self.temperature_feedback.setText(ErrorMessage.InvalidTemperature())
                    return

            if self.sequencer_type == Sequencer.Dynamic():
                temps = self._get_dynamic_temp(text)
                if temps is None:
                    self.temperature_feedback.setText(ErrorMessage.InvalidTemperature())
                    return

            self._custom_parameter_handler.set_temperature(temps)
            self._insert_tests_to_selected_list()
            self._update_test_list()
        self._verify()

    def _update_test_list(self):
        self.availableTests.clear()
        alltests = self._get_available_tests()
        for t in alltests:
            self.availableTests.addItem(t.name)
            self._fill_standard_parameter_handler(t.name, t.name)

    def _fill_standard_parameter_handler(self, test_name, test_instance_name):
        self.input_parameters, self.output_parameters = self._get_in_output_paramters(test_name)
        self._standard_parameter_handler.add_test(test_instance_name, test_name, self.input_parameters, self.output_parameters)

    def _validate_temperature_input(self, text, pattern):
        index = text.rfind(pattern)
        if index == -1:
            return

        text_list = list(text)
        text_list[index] = ''
        if not text_list[len(text_list) - 1].isdigit():
            text_list[len(text_list) - 1] = ''

        self.temperature.setText(''.join(text_list))

    def _get_dynamic_temp(self, text):
        temp_vars = []
        try:
            self._validate_temperature_input(text, ',,')
            temps = text.split(',')
            if len(temps) == 0:
                return None

            for i in temps:
                if i == '-':
                    return

                if i != '':
                    temp_vars.append(int(i))

        except ValueError:
            self._validate_temperature_input(text, '--')
            return None

        return temp_vars

    def _get_available_tests(self):
        available_tests = []
        tests = self.project_info.get_tests_from_db(self.hardware.currentText(),
                                                    self.base.currentText())
        if not self.temperature.text():
            return tests

        if self.sequencerType.currentText() == Sequencer.Static():
            temps = [int(self.temperature.text())]
        else:
            temps = self._get_dynamic_temp(self.temperature.text())

        if temps is None:
            return tests

        for test in tests:
            min, max = self.project_info.get_test_temp_limits(test.name, self.project_info.active_hardware, self.project_info.active_base)
            for temp in temps:
                if temp > (min - 1) and temp < max + 1 and \
                   test not in available_tests:
                    available_tests.append(test)

        return available_tests

    def _set_sample_visible_mode(self, is_visible):
        self.sample.setVisible(is_visible)
        self.sample_label.setVisible(is_visible)
        self.one_label.setVisible(is_visible)

    def _verify(self):
        success = True
        self.usertext_feedback.setText('')
        self.target_feedback.setText('')
        self.temperature_feedback.setText('')
        self._update_feedback('')

        if self.base.currentText() == 'PR':
            self._set_sample_visible_mode(False)
        else:
            self._set_sample_visible_mode(True)

        if not self.target.currentText():
            self.target_feedback.setText(ErrorMessage.TargetMissed())
            success = False

        if not self.selectedTests.rowCount():
            self._update_feedback(ErrorMessage.EmtpyTestList())
            success = False

        if not self._is_dynamic_range_valid:
            self._update_feedback(ErrorMessage.NoValidTestRange())
            success = False

        if not self.temperature.text():
            self.temperature_feedback.setText(ErrorMessage.TemperatureNotValidated())
            success = False

        if not self._custom_parameter_handler.are_all_tests_valid():
            self._update_feedback(ErrorMessage.ParameterNotValid())
            success = False

        if not self._are_sbins_valid():
            self._update_feedback(ErrorMessage.SbinInvalidOrMissing())
            success = False

        if not self._binning_handler.verify():
            self._update_feedback(ErrorMessage.BinTableNotfilled())
            success = False

        if success:
            self.usertext_feedback.setText('')
            self.target_feedback.setText('')
            self.temperature_feedback.setText('')
            self._update_feedback('')
            self.OKButton.setEnabled(True)
        else:
            self.OKButton.setEnabled(False)

    def _are_sbins_valid(self) -> bool:
        iterator = QTreeWidgetItemIterator(self.binning_tree, flags=QTreeWidgetItemIterator.NoChildren)
        while iterator.value():
            item = iterator.value()
            if not item.text(1):
                return False

            output = self._custom_parameter_handler.get_output_parameter_from_test_instance(item.text(0))
            if not output.is_bin_parameter_valid():
                return False

            iterator += 1

        return True

    @property
    def program_name(self):
        return f'Prog_{self.hardware.currentText()}_{self.base.currentText()}_{self.target.currentText()}_{self.usertext.text()}'

    @property
    def sequencer_type(self):
        return self.sequencerType.currentText()

    def _update_feedback(self, message):
        if message:
            self.Feedback.setText(message)
        else:
            self.Feedback.setText('')

    @staticmethod
    def _generate_color(color: tuple):
        return QtGui.QBrush(QtGui.QColor(color[0], color[1], color[2]))

    def _set_widget_color(self, item, color):
        item.setBackground(self._generate_color(color))
        item.setForeground(QtCore.Qt.black)

    def _display_active_test(self):
        if len(self.selectedTests.selectedItems()):
            parameter_handler = self._custom_parameter_handler
            test_instance = self._selected_test_instance()
        else:
            parameter_handler = self._standard_parameter_handler
            test_instance = self.availableTests.selectedItems()[0].text()

        parameter_handler.display_test(test_instance, self.parametersInput, self.parametersOutput)

    @staticmethod
    def _get_text(value, fmt):
        return ('%' + fmt) % float(value)

    def _get_test_parameters(self, test_name):
        return self.project_info.get_test_table_content(self._extract_base_test_name(test_name), self.project_info.active_hardware, self.project_info.active_base)

    def _resize_table_cell(self, parameter_table, cell, item):
        font = QtGui.QFont()
        metric = QtGui.QFontMetrics(font)
        text_size = metric.boundingRect(item.text()).width()
        colum_size = 1
        if (text_size + colum_size) > self.cell_size:
            self.cell_size = text_size + colum_size

        parameter_table.setColumnWidth(cell, self.cell_size)

    @QtCore.pyqtSlot(QtWidgets.QTableWidgetItem)
    def _double_click_handler_input_param(self, item):
        test_instance = self.selectedTests.item(self.selectedTests.currentRow(), 1).text()
        param_name = self.parametersInput.item(item.row(), 0).text()
        param = self._custom_parameter_handler.edit_input_parameter(test_instance, param_name, item.column(), lambda: self.edit_param_complete(param))

    @QtCore.pyqtSlot(QtWidgets.QTableWidgetItem)
    def _double_click_handler_output_param(self, item):
        test_instance = self.selectedTests.item(self.selectedTests.currentRow(), 1).text()
        param_name = self.parametersOutput.item(item.row(), 0).text()
        param = self._custom_parameter_handler.edit_output_parameter(test_instance, param_name, item.column(), lambda: self.edit_param_complete(param))

    def edit_param_complete(self, param):
        self._validate_parameter(param)
        self._verify()

    def _create_checkable_cell(self, test_name, table, item, validator):
        column = item.column()
        row = item.row()
        checkable_widget = QtWidgets.QLineEdit()
        checkable_widget.setText(item.text())
        checkable_widget.setValidator(validator)

        table.setCellWidget(row, column, checkable_widget)
        checkable_widget.editingFinished.connect(lambda row=row, column=column,
                                                 checkable_widget=checkable_widget, table=table:
                                                 self._edit_cell_done(test_name, table, checkable_widget, row, column))

    def _edit_cell_done(self, test_name, table, checkable_widget, row, column):
        description = checkable_widget.text()
        if self._is_description_valid(table, description):
            self._custom_parameter_handler.update_test_name(test_name, description)
            self.selectedTests.item(row, column).setText(str(checkable_widget.text()))
        else:
            self._update_feedback(ErrorMessage.TestDescriptionNotUnique())

        self._update_row(row)
        if not self.selectedTests.selectedItems():
            self.parametersInput.setRowCount(0)
            self.parametersOutput.setRowCount(0)

        self._populate_binning_tree()
        self._verify()

    @staticmethod
    def _is_description_valid(table, description):
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if not item:
                continue

            if item.text() != description:
                continue

            return False

        return True

    def _update_row(self, row):
        test_name = self.selectedTests.item(row, 0).text()
        test_description = self.selectedTests.item(row, 1).text()

        self.selectedTests.blockSignals(True)
        self.selectedTests.removeRow(row)
        self.selectedTests.insertRow(row)
        self._insert_test_tuple_without_validation(row, test_name, test_description)
        self.selectedTests.blockSignals(False)

    def _insert_test_tuple_without_validation(self, row, test_name, test_description):
        test_base_item = self._generate_test_name_item(test_name)
        test_name_item = self._generate_test_description_item(test_description)

        self.selectedTests.setItem(row, 0, test_base_item)
        self.selectedTests.setItem(row, 1, test_name_item)

    def _update_selected_test_list(self):
        self._validate_tests_parameters()
        self._insert_tests_to_selected_list()

    def _insert_tests_to_selected_list(self):
        self.selectedTests.blockSignals(True)
        self.selectedTests.setRowCount(len(self._custom_parameter_handler.get_test_names()))
        for index, test in enumerate(self._custom_parameter_handler.get_tests()):
            self._validate_test_parameters(test.get_test_name())
            self._insert_test_tuple_items(index, test.get_test_base(), test.get_test_name(), test.get_valid_flag())

        self.selectedTests.blockSignals(False)

    def _validate_tests_parameters(self):
        if not self.prog_name:
            return

        test_targets = self.project_info.get_changed_test_targets(self.hardware.currentText(), self.base.currentText(), self.prog_name)
        if not test_targets:
            return

        test_names = set([test.test for test in test_targets])
        self._custom_parameter_handler.validate_tests(test_names)

    def _insert_test_tuple_items(self, row, test_name, test_description, valid):
        test_base_item = self._generate_test_name_item(test_name)
        test_name_item = self._generate_test_description_item(test_description)

        if valid in (ParameterState.Invalid(), ParameterState.Changed()):
            self._set_widget_color(test_base_item, RED)
            self._set_widget_color(test_name_item, RED)

        if valid == ParameterState.PartValid():
            self._set_widget_color(test_base_item, ORANGE)
            self._set_widget_color(test_name_item, ORANGE)

        self.selectedTests.setItem(row, 0, test_base_item)
        self.selectedTests.setItem(row, 1, test_name_item)

    def _validate_parameter(self, parameter):
        if not parameter.is_valid_value():
            self._update_feedback(ErrorMessage.OutOfRange())
        else:
            self._update_feedback('')

        self._display_active_test()

    def _add_test_tuple_items(self, test_name):
        indexed_test = self._generate_test_name(test_name)
        test_name = indexed_test.split('_')[0]

        input_parameters, output_parameters = self._get_in_output_paramters(test_name)
        self._custom_parameter_handler.add_test(indexed_test, test_name, input_parameters, output_parameters)
        test_names = self._custom_parameter_handler.get_test_names()

        self.selectedTests.setRowCount(len(test_names))
        item_name = self._generate_test_name_item(test_name)
        item_description = self._generate_test_description_item(indexed_test)
        pos = len(test_names) - 1
        self.selectedTests.setItem(pos, 0, item_name)
        self.selectedTests.setItem(pos, 1, item_description)
        bin_info = self._custom_parameter_handler.get_binning_info_for_test(indexed_test)
        self._add_tests_to_bin_table(bin_info)

    def _generate_test_name(self, test_base):
        test_names = self._custom_parameter_handler.get_test_names()
        test_indexes = [test.split('_')[1] for test in test_names if test_base in test]
        numbers = []
        for test_index in test_indexes:
            try:
                numbers.append(int(test_index))
            except Exception:
                pass

        numbers.sort()
        if not len(numbers):
            return f"{test_base}_{1}"

        return f"{test_base}_{numbers[-1] + 1}"

    @staticmethod
    def _generate_test_description_item(text):
        description_item = QtWidgets.QTableWidgetItem(text)
        description_item.setFlags(QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        return description_item

    @staticmethod
    def _generate_test_name_item(text):
        name_item = QtWidgets.QTableWidgetItem(text)
        # name should not be editable
        name_item.setFlags(QtCore.Qt.NoItemFlags | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
        return name_item

    def _populate_binning_tree(self):
        self.binning_tree.clear()
        self._bin_table.clear_alarm_table()
        binning_infos = self._custom_parameter_handler.binning_information()
        for test in binning_infos:
            self._add_tests_to_bin_table(test)

    def _add_tests_to_bin_table(self, test: TestParameters):
        self.binning_tree.blockSignals(True)
        parent = QTreeWidgetItem(self.binning_tree)
        parent.setExpanded(True)
        parent.setText(0, test['name'])
        test_alarm = f'{test["description"]}_ALARM'
        parent.setText(1, test_alarm)
        self._bin_table.add_alarm_bin(test_alarm, BINGROUPS[3], '')

        self._add_binning_item(test['description'], test['output_parameters'], parent)
        self.binning_tree.blockSignals(False)

    def _add_binning_item(self, description, out_params, parent):
        for key, value in out_params.items():
            item = QTreeWidgetItem()
            item.setText(0, description + '_' + key)
            self._set_bin_flag(item, value.get_field_state())
            # TODO: uncomment this if there is not need to assign output to soft-bins automatically
            value: OutputParameter = value
            bin_info = value.get_bin_infos()
            if bin_info.bin_name:
                item.setText(1, bin_info.bin_name)
            else:
                # TODO: remove this afterwards
                item.setText(1, self.binning_table.item(0, 0).text())

            parent.addChild(item)

    def _set_bin_flag(self, item, validity):
        if validity in (ParameterState.Valid(), ParameterState.Changed(), ParameterState.PartValid()):
            return

        color = RED
        flags = QtCore.Qt.NoItemFlags
        if validity == ParameterState.New():
            color = GREEN
            flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled

        item.setFlags(flags)
        self._set_tree_item_color(item, 0, color)
        self._set_tree_item_color(item, 1, color)
        self._set_tree_item_color(item, 2, color)

    def _set_tree_item_color(self, item, col, color):
        item.setBackground(col, self._generate_color(color))
        item.setForeground(col, QtCore.Qt.black)

    @QtCore.pyqtSlot(QTableWidgetItem)
    def _binning_table_item_double_clicked(self, item: QTableWidgetItem):
        self._binning_handler._create_input_cell(self.binning_table, item)

    def _update_binning_tree_items(self):
        iterator = QTreeWidgetItemIterator(self.binning_tree, flags=QTreeWidgetItemIterator.NoChildren)
        while iterator.value():
            item = iterator.value()
            if not item.text(1):
                iterator += 1
                continue

            output = self._custom_parameter_handler.get_output_parameter_from_test_instance(item.text(0))
            if self._bin_table.does_bin_exist(output.get_bin_infos().bin_name):
                self._set_tree_item_color(item, 1, RED)
                output.set_bin_parameter_validity(False)
            else:
                # in case the item ist not validated because the bin name is not defined and
                # we do an import where the sbin name is defined, then we validate
                if not output.is_bin_parameter_valid():
                    self._update_bin_tree_element(item, item.text(1))
                    output.set_bin_parameter_validity(True)
                    # TODO: recursive call --> what can go wrong !!
                    self._update_binning_tree_items()
                    break

            iterator += 1

        self._verify()

    @staticmethod
    def _is_pass_grade(text):
        grade = int(text)
        return grade >= 1 and grade <= 9

    @staticmethod
    def _update_binning_tree(text, item, pos):
        item.setText(pos, text)

    @staticmethod
    def _get_bin_result(text):
        if text == 'Fail':
            return Result.Fail()
        else:
            return Result.Pass()

    def _get_binning_structure(self, item: QTreeWidgetItem):
        if item.childCount() != 0:
            return

        output_name = item.text(0).split('_')
        test_name = output_name[0] + '_' + output_name[1]
        param_name = item.text(0).replace(test_name, '')
        return self._custom_parameter_handler.get_test_outputs_parameters(test_name)[param_name[1:]]

    @staticmethod
    def _get_binning_params(item):
        return (item.text(1), item.text(2), item.text(3))

    def _get_temperature_value(self):
        return self.temperature.text() if self.sequencer_type == Sequencer.Static() else self._get_dynamic_temp(self.temperature.text())

    def _get_caching_policy_value(self):
        if self.cacheDrop.isChecked():
            return "drop"
        if self.cacheStore.isChecked():
            return "store"
        return "disable"

    @QtCore.pyqtSlot()
    def _import_bin_table(self):
        import_file = FileSystemOperator(os.path.join(self.project_info.project_directory, 'src',
                                                      self.hardware.currentText(), self.base.currentText()), self.project_info.parent)
        file_name = import_file.get_path()
        if not file_name:
            return

        self._load_bin_table(file_name)

    def _load_bin_table(self, file_name):
        self._bin_table.load_bin_table(file_name)
        self._binning_handler.update()
        self._update_binning_tree_items()

    @QtCore.pyqtSlot()
    def _add_new_bin(self):
        row = self.binning_table.rowCount()
        self.binning_table.setRowCount(row + 1)
        sb_name, sb_num = self._bin_table.generate_bin_identrifiers()

        sb_group = BINGROUPS[1]
        sb_description = ''
        self._binning_handler.add_bin(row, sb_name, sb_num, sb_group, sb_description)

    @QtCore.pyqtSlot()
    def _remove_selected_bin(self):
        selected_bins = self.binning_table.selectedItems()
        for selected_bin in selected_bins:
            row = selected_bin.row()
            self._bin_table.remove_bin(self.binning_table.item(row, 0).text())
            self.binning_table.removeRow(row)

    def _update_output_parameter_bin_information(self):
        iterator = QTreeWidgetItemIterator(self.binning_tree, flags=QTreeWidgetItemIterator.NoChildren)
        while iterator.value():
            item = iterator.value()
            test_instance_name = item.text(0)
            output = self._custom_parameter_handler.get_output_parameter_from_test_instance(test_instance_name)
            bin_item = self.binning_table.findItems(item.text(1), QtCore.Qt.MatchExactly)[0]
            row = bin_item.row()
            output.set_bin_infos(self.binning_table.item(row, 0).text(),
                                 self.binning_table.item(row, 1).text(),
                                 self.binning_table.item(row, 2).text(),
                                 self.binning_table.item(row, 3).text())
            iterator += 1

    def _update_test_bin(self):
        iterator = QTreeWidgetItemIterator(self.binning_tree, flags=QTreeWidgetItemIterator.HasChildren)
        while iterator.value():
            item = iterator.value()
            test = self._custom_parameter_handler.get_test_from_test_instance_name(item.child(0).text(0))
            test.set_sbin(self._bin_table.get_alarm_bin_num(item.text(1)))
            iterator += 1

    def _save_configuration(self):
        self._update_output_parameter_bin_information()
        self._update_test_bin()
        definition = self._custom_parameter_handler.build_defintion()
        if not self.read_only and self.enable_edit:
            owner, count = self._get_test_program_infos()
            self.prog_name = self._generate_test_program_name(owner, count)

            self.target_prefix = f"{self.target.currentText()}_{self.owner}_{count}"

            self.project_info.insert_program(self.prog_name, self.hardware.currentText(), self.base.currentText(), self.target.currentText(),
                                             self.usertext.text(), self.sequencer_type, self._get_temperature_value(),
                                             definition, owner, self.project_info.get_program_owner_element_count(owner), self.target_prefix,
                                             self.cacheType.currentText(), self._get_caching_policy_value())
        else:
            self.project_info.update_changed_state_test_targets(self.hardware.currentText(), self.base.currentText(), self.prog_name)
            self.project_info.update_program(self.prog_name, self.hardware.currentText(), self.base.currentText(),
                                             self.target.currentText(), self.usertext.text(), self.sequencer_type,
                                             self._get_temperature_value(), definition, self.owner, self._get_target_name(),
                                             self.cacheType.currentText(), self._get_caching_policy_value())

        self._bin_table.create_binning_file(os.path.join(self.project_info.project_directory,
                                                         'src',
                                                         self.hardware.currentText(),
                                                         self.base.currentText(),
                                                         f'{self.prog_name}_binning.json'))

        self.accept()

    def _get_test_program_infos(self):
        owner = f"{self.hardware.currentText()}_{self.base.currentText()}_{self.target.currentText()}_{self.owner}"
        count = self.project_info.get_program_owner_element_count(owner) + 1
        return owner, count

    def _generate_test_program_name(self, owner, count):
        return f'{os.path.basename(self.project_info.project_directory)}_{owner}_{count}'

    def _get_target_name(self):
        owner_split = self.owner.split('_')
        index = -1
        for i, text in enumerate(owner_split):
            if not text == self.target.currentText():
                continue

            index = i
            break

        target_name = self.target.currentText()
        for i in range(index + 1, len(owner_split)):
            target_name += '_' + owner_split[i]

        target_name += '_' + self.prog_name[-1]

        return target_name

    def _cancel(self):
        self.reject()

    def __make_lambda(self, gp_fun_name):
        return lambda: self._selected_gp_fun(gp_fun_name)

    def _get_input_parameter_types(self) -> dict:
        item = self.selectedTests.selectedItems()[0]
        if item.row() == 0:
            return {ResolverTypes.Static(): self._static_selected}

        menu_entries = {ResolverTypes.Static(): self._static_selected, ResolverTypes.Local(): self._local_selected}

        # ToDo: Use displayname instead of objectname!
        for gpfun in self._available_gp_functions:
            menu_entries[gpfun] = self.__make_lambda(gpfun)

        return menu_entries

    def _set_out_params(self):
        action = self.sender()
        parent = action.parent()
        item = self.parametersInput.currentItem()
        input_name = self.parametersInput.item(item.row(), 0).text()
        parameter = self._custom_parameter_handler.get_input_parameter(self._selected_test_instance(), input_name)
        parameter.set_value(f'{parent.title()}.{action.text()}')
        self._display_active_test()

    def _selected_test_instance(self):
        row = self.selectedTests.selectedItems()[0].row()
        return self.selectedTests.item(row, 1).text()

    def _static_selected(self):
        type_item = self.parametersInput.currentItem()
        type_item.setText(ResolverTypes.Static())
        self._update_value_cell(type_item, ParameterEditability.Editable(), ResolverTypes.Static())

    def _local_selected(self):
        type_item = self.parametersInput.currentItem()
        type_item.setText(ResolverTypes.Local())
        self._update_value_cell(type_item, ParameterEditability.Selectable(), ResolverTypes.Local())

    def _selected_gp_fun(self, func_name: str):
        type_item = self.parametersInput.currentItem()
        resolver_type = f"{ResolverTypes.Remote()}:{func_name}"
        type_item.setText(resolver_type)
        self._update_value_cell(type_item, ParameterEditability.Editable(), resolver_type)

    def _update_value_cell(self, type_item, editability, resolver_type: ResolverTypes):
        value_item = self.parametersInput.item(type_item.row(), InputFieldsPosition.Value)
        self._set_editability(value_item, editability)
        input_name = self.parametersInput.item(type_item.row(), 0).text()

        self._update_parameter_type(input_name, resolver_type, editability)
        self._display_active_test()

    def _update_parameter_type(self, input_name: str, resolver_type: str, editability: ParameterEditability):
        parameter = self._custom_parameter_handler.get_input_parameter(self._selected_test_instance(), input_name)
        parameter.set_type(resolver_type)
        parameter.set_value_editability(editability)

    @staticmethod
    def _set_editability(item, editability: ParameterEditability):
        if editability == ParameterEditability.Selectable():
            item.setFlags(QtCore.Qt.ItemIsEnabled)
        elif editability == ParameterEditability.Editable():
            item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable)
        else:
            item.setFlags(QtCore.Qt.NoItemFlags)

    def _context_menu_input_params(self, point):
        item = self.parametersInput.itemAt(point)
        if not item:
            return

        column = item.column()
        row = item.row()
        if column not in (InputFieldsPosition.Type(), InputFieldsPosition.Value()) or row == 0:
            return

        type = self.parametersInput.item(row, InputFieldsPosition.Type()).text()
        if column == InputFieldsPosition.Value() and type == ResolverTypes.Local():
            input_name = self.parametersInput.item(row, 0).text()
            self._create_value_menu(self._get_local_test_output_parameters_names(input_name))
        elif column == InputFieldsPosition.Type():
            self._create_type_menu(self._get_input_parameter_types())

        self._verify()

    def _get_local_test_output_parameters_names(self, input_name):
        available_tests = {}
        current_item = self.selectedTests.selectedItems()[0]
        test_name = self.selectedTests.item(current_item.row(), 1).text()
        test_out_params = self._custom_parameter_handler.get_tests_outputs_parameters()
        test_in_param = self._custom_parameter_handler.get_input_parameter(test_name, input_name)

        for test_out_param in test_out_params:
            for test, out_param in test_out_param.items():
                if test == test_name:
                    return available_tests

                available_tests[test] = []
                for output in out_param:
                    if not self._custom_parameter_handler.is_valid_range(test, test_in_param, output):
                        continue

                    available_tests[test].append(output)

        return available_tests

    def _create_type_menu(self, components):
        menu = QtWidgets.QMenu(self)
        for pd, func in components.items():
            item = menu.addAction(pd)
            item.triggered.connect(func)
            menu.addSeparator()

        menu.exec_(QtGui.QCursor.pos())

    def _create_value_menu(self, components):
        menu = QtWidgets.QMenu(self)
        for test_name, tests in components.items():
            menu.addMenu(self._generate_test_menu(test_name, tests, menu))

        menu.exec_(QtGui.QCursor.pos())

    def _generate_test_menu(self, test_name, tests, parent):
        menu = QtWidgets.QMenu(test_name, parent)
        if not len(tests):
            menu.setEnabled(False)
        for test in tests:
            item = menu.addAction(test)
            item.triggered.connect(self._set_out_params)

        return menu


def new_program_dialog(project_info, owner, parent):
    testProgramWizard = TestProgramWizard(project_info, owner, parent)
    testProgramWizard.exec_()
    del(testProgramWizard)
