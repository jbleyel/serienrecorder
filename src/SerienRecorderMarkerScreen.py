# coding=utf-8

# This file contains the SerienRecoder Marker Screen
from __future__ import print_function
import time, cPickle as pickle

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ConfigList import ConfigListScreen, ConfigList
from Components.config import config, ConfigInteger, getConfigListEntry, ConfigText, ConfigYesNo, configfile, ConfigSelection, NoSave, ConfigClock
from Components.MenuList import MenuList

from Screens.HelpMenu import HelpableScreen
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox

from Tools.Directories import fileExists

from enigma import ePicLoad, eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER, loadPNG
from skin import parseColor

if fileExists("/usr/lib/enigma2/python/Plugins/SystemPlugins/Toolkit/NTIVirtualKeyBoard.pyo"):
	from Plugins.SystemPlugins.Toolkit.NTIVirtualKeyBoard import NTIVirtualKeyBoard
else:
	from Screens.VirtualKeyBoard import VirtualKeyBoard as NTIVirtualKeyBoard

from SerienRecorderScreenHelpers import serienRecBaseScreen, InitSkin, skinFactor, setMenuTexts, buttonText_na
from SerienRecorder import serienRecDataBaseFilePath, getCover, \
	serienRecMainPath, VPSPluginAvailable, serienRecCheckForRecording

from SerienRecorderHelpers import STBHelpers, TimeHelpers, getDirname, isVTI
from SerienRecorderDatabase import SRDatabase
from SerienRecorderEpisodesScreen import serienRecEpisodes
from SerienRecorderSeriesServer import SeriesServer
from SerienRecorderLogWriter import SRLogger

# Tageditor
from Screens.MovieSelection import getPreferredTagEditor

class serienRecMarker(serienRecBaseScreen, Screen, HelpableScreen):
	def __init__(self, session, toBeSelect=None):
		serienRecBaseScreen.__init__(self, session)
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.session = session
		self.picload = ePicLoad()
		self.skin = None
		self.displayMode = 0
		self.displayTimer = None
		self.displayTimer_conn = None
		self.chooseMenuList = MenuList([], enableWrapAround=True, content=eListboxPythonMultiContent)
		self.chooseMenuList_popup = MenuList([], enableWrapAround=True, content=eListboxPythonMultiContent)
		self.database = SRDatabase(serienRecDataBaseFilePath)
		self.staffel_liste = []
		self.sender_liste = []
		self.AbEpisode = 0
		self.columnWidth = int(config.plugins.serienRec.markerColumnWidth.value)

		if config.plugins.serienRec.firstscreen.value == "0":
			self.showMainScreen = True
		else:
			self.showMainScreen = False

		actions = {
			"ok"            : (self.keyOK, "zur Staffelauswahl"),
			"cancel"        : (self.keyCancel, "zurück zur Serienplaner-Ansicht"),
			"red"	        : (self.keyRed, "umschalten ausgewählter Serien-Marker aktiviert/deaktiviert"),
			"red_long"      : (self.keyRedLong, "ausgewählten Serien-Marker löschen"),
			"green"         : (self.keyGreen, "zur Senderauswahl"),
			"yellow"        : (self.keyYellow, "Sendetermine für ausgewählte Serien anzeigen"),
			"blue"	        : (self.keyBlue, "Ansicht Timer-Liste öffnen"),
			"info"	        : (self.keyCheck, "Suchlauf für Timer starten"),
			"left"          : (self.keyLeft, "zur vorherigen Seite blättern"),
			"right"         : (self.keyRight, "zur nächsten Seite blättern"),
			"up"            : (self.keyUp, "eine Zeile nach oben"),
			"down"          : (self.keyDown, "eine Zeile nach unten"),
			"menu"          : (self.markerSetup, "Menü für Serien-Einstellungen öffnen"),
			"menu_long"     : (self.recSetup, "Menü für globale Einstellungen öffnen"),
			"startTeletext" : (self.wunschliste, "Informationen zur ausgewählten Serie auf Wunschliste anzeigen"),
			#"startTeletext_long" : (self.resetTransmissions, "Ausstrahlungstermine auf dem SerienServer zurücksetzen"),
			"0"		        : (self.readLogFile, "Log-File des letzten Suchlaufs anzeigen"),
			"1"		        : (self.searchSeries, "Serie manuell suchen"),
			"2"		        : (self.changeTVDBID, "TVDB-ID ändern"),
			"3"		        : (self.showProposalDB, "Liste der Serien/Staffel-Starts anzeigen"),
			"4"		        : (self.serieInfo, "Informationen zur ausgewählten Serie anzeigen"),
			"5"		        : (self.episodeList, "Episoden der ausgewählten Serie anzeigen"),
			"6"		        : (self.showConflicts, "Liste der Timer-Konflikte anzeigen"),
			"7"		        : (self.showWishlist, "Merkzettel (vorgemerkte Folgen) anzeigen"),
			"8"		        : (self.updateMarkers, "Serien-Marker aktualisieren"),
			"9"		        : (self.disableAll, "Alle Serien-Marker für diese Box-ID deaktivieren"),
		}

		if not self.showMainScreen:
			actions["cancel_long"] = (self.keyExit, "zurück zur Serienplaner-Ansicht")

		self["actions"] = HelpableActionMap(self, "SerienRecorderActions", actions, -1)
		self.helpList[0][2].sort()
		
		self["helpActions"] = ActionMap(["SerienRecorderActions",], {
			"displayHelp"      : self.showHelp,
			"displayHelp_long" : self.showManual,
		}, 0)

		self.setupSkin()
		
		self.modus = "menu_list"
		self.changesMade = False
		self.loading = True
		self.selected_serien_wlid = toBeSelect
		
		self.onLayoutFinish.append(self.setSkinProperties)
		self.onLayoutFinish.append(self.readSerienMarker)
		self.onClose.append(self.__onClose)

	def callHelpAction(self, *args):
		HelpableScreen.callHelpAction(self, *args)
		
	def setSkinProperties(self):
		super(self.__class__, self).setSkinProperties()

		self['text_green'].setText("Sender auswählen")
		self['text_ok'].setText("Staffel(n) auswählen")
		self['text_yellow'].setText("Sendetermine")
		self.num_bt_text[1][0] = "Serie suchen"
		self.num_bt_text[2][0] = "TVDB-ID ändern"
		self.num_bt_text[0][1] = "Episoden-Liste"
		self.num_bt_text[2][2] = "Timer suchen"
		self.num_bt_text[3][1] = "Marker aktualisieren"
		self.num_bt_text[4][1] = "Alle deaktivieren"
		self.num_bt_text[4][2] = "Setup Serie/global"
		self['text_red'].setText("Ein/Löschen")
		self['text_blue'].setText("Timer-Liste")
		if not self.showMainScreen:
			self.num_bt_text[0][2] = "Exit/Serienplaner"

		super(self.__class__, self).startDisplayTimer()

	def setupSkin(self):
		self.skin = None
		InitSkin(self)
		
		#normal
		self.chooseMenuList.l.setFont(0, gFont('Regular', 20 + int(config.plugins.serienRec.listFontsize.value)))
		self.chooseMenuList.l.setItemHeight(int(70*skinFactor))
		self['menu_list'] = self.chooseMenuList
		self['menu_list'].show()

		# popup
		self.chooseMenuList_popup.l.setFont(0, gFont('Regular', 20 + int(config.plugins.serienRec.listFontsize.value)))
		self.chooseMenuList_popup.l.setItemHeight(int(25*skinFactor))
		self['popup_list'] = self.chooseMenuList_popup
		self['popup_list'].hide()

		if config.plugins.serienRec.showCover.value:
			self['cover'].show()

		if not config.plugins.serienRec.showAllButtons.value:
			self['bt_red'].show()
			self['bt_green'].show()
			self['bt_ok'].show()
			self['bt_yellow'].show()
			self['bt_blue'].show()
			self['bt_exit'].show()
			self['bt_text'].show()
			self['bt_epg'].show()
			self['bt_info'].show()
			self['bt_menu'].show()
			
			self['text_red'].show()
			self['text_green'].show()
			self['text_ok'].show()
			self['text_yellow'].show()
			self['text_blue'].show()
			self['text_0'].show()
			self['text_1'].show()
			self['text_2'].show()
			self['text_3'].show()
			self['text_4'].show()

	def markerSetup(self):
		if self['menu_list'].getCurrent() is None:
			return
		serien_id = self['menu_list'].getCurrent()[0][0]
		serien_name = self['menu_list'].getCurrent()[0][1]
		self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]
		serien_fsid = self['menu_list'].getCurrent()[0][13]
		self.session.openWithCallback(self.setupFinished, serienRecMarkerSetup, serien_name, self.selected_serien_wlid, serien_id, serien_fsid)

	def setupFinished(self, result):
		if result:
			self.changesMade = True
			if config.plugins.serienRec.tvplaner_full_check.value:
				config.plugins.serienRec.tvplaner_last_full_check.value = int(0)
				config.plugins.serienRec.tvplaner_last_full_check.save()
				configfile.save()
		self.readSerienMarker(self.selected_serien_wlid)
		return

	def getCurrentSelection(self):
		serien_name = self['menu_list'].getCurrent()[0][1]
		serien_wlid = self['menu_list'].getCurrent()[0][2]
		serien_fsid = self['menu_list'].getCurrent()[0][13]
		return serien_name, serien_wlid, serien_fsid

	def updateMarkers(self):
		self.session.openWithCallback(self.executeUpdateMarkers, MessageBox, "Sollen die Namen der Serien-Marker aktualisieren werden?", MessageBox.TYPE_YESNO)

	def executeUpdateMarkers(self, execute):
		if execute:
			updatedMarkers = self.database.updateSeriesMarker(True)
			self.readSerienMarker()
			message = "Es musste kein Serien-Marker aktualisiert werden."
			if len(updatedMarkers) > 0:
				message = "Es wurden %d Serien-Marker aktualisiert.\n\nEine Liste der geänderten Marker wurde ins Log geschrieben." % len(updatedMarkers)

			self.session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=10)

	def changeTVDBID(self):
		if self.loading:
			return

		from SerienRecorderScreenHelpers import EditTVDBID
		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		editTVDBID = EditTVDBID(self, self.session, serien_name, serien_wlid, serien_fsid)
		editTVDBID.changeTVDBID()

	def serieInfo(self):
		if self.loading or self['menu_list'].getCurrent() is None:
			return

		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		if serien_wlid:
			from SerienRecorderSeriesInfoScreen import serienRecShowInfo
			self.session.open(serienRecShowInfo, serien_name, serien_wlid, serien_fsid)
			#self.session.open(MessageBox, "Diese Funktion steht in dieser Version noch nicht zur Verfügung!",
			#				  MessageBox.TYPE_INFO, timeout=10)

	def episodeList(self):
		if self.modus == "menu_list" and self['menu_list'].getCurrent():
			(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
			if serien_wlid:
				self.session.open(serienRecEpisodes, serien_name, serien_wlid)

	def wunschliste(self):
		if self['menu_list'].getCurrent() is None:
			return
		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		super(self.__class__, self).wunschliste(serien_wlid)

	def resetTransmissions(self):
		if self['menu_list'].getCurrent() is None:
			return
		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		if serien_wlid:
			SeriesServer().resetLastEPGUpdate(serien_wlid)

	def setupClose(self, result):
		super(self.__class__, self).setupClose(result)

		if result[1]:
			self.readSerienMarker()

	def getCover(self):
		if self.loading or self['menu_list'].getCurrent() is None:
			return

		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		getCover(self, serien_name, serien_wlid, serien_fsid)

	def readSerienMarker(self, selectedSeriesWLID=None):
		if selectedSeriesWLID:
			self.selected_serien_wlid = selectedSeriesWLID

		numberOfDeactivatedSeries, markerList = self.getMarkerList(self.database)
		self['title'].setText("Serien-Marker - %d/%d Serien vorgemerkt." % (len(markerList)-numberOfDeactivatedSeries, len(markerList)))
		if len(markerList) != 0:
			self.chooseMenuList.setList(map(self.buildList, markerList))
			if self.selected_serien_wlid:
				try:
					idx = zip(*markerList)[2].index(str(self.selected_serien_wlid))
					self['menu_list'].moveToIndex(idx)
				except Exception:
					pass
			self.loading = False
			self.setMenuKeyText()
			self.getCover()

	@staticmethod
	def getMarkerList(database):
		markerList = []
		numberOfDeactivatedSeries = 0
		
		markers = database.getAllMarkers(True if config.plugins.serienRec.markerSort.value == '1' else False)		
		for marker in markers:
			(ID, Serie, Info, Url, AufnahmeVerzeichnis, AlleStaffelnAb, alleSender, Vorlaufzeit, Nachlaufzeit, AnzahlAufnahmen, preferredChannel, useAlternativeChannel, AbEpisode, TimerForSpecials, ErlaubteSTB, ErlaubteStaffelCount, fsID) = marker
			if alleSender:
				sender = ['Alle',]
			else:
				sender = database.getMarkerChannels(Url, False)

			if AlleStaffelnAb == -2: 		# 'Manuell'
				staffeln = ['Manuell',]
			elif AlleStaffelnAb == 0:		# 'Alle'
				staffeln = ['Alle',]
			else:
				staffeln = []
				if ErlaubteStaffelCount > 0:
					staffeln = database.getAllowedSeasons(ID, AlleStaffelnAb)
					staffeln.sort()
				if AlleStaffelnAb < 999999:
					staffeln.append('ab %s' % AlleStaffelnAb)
				if AbEpisode > 0:
					staffeln.insert(0, '0 ab E%s' % AbEpisode)
				if bool(TimerForSpecials):
					staffeln.insert(0, 'Specials')

			if useAlternativeChannel == -1:
				useAlternativeChannel = config.plugins.serienRec.useAlternativeChannel.value
			
			SerieAktiviert = True
			if ErlaubteSTB is not None and not (ErlaubteSTB & (1 << (int(config.plugins.serienRec.BoxID.value) - 1))):
				numberOfDeactivatedSeries += 1
				SerieAktiviert = False

			staffeln = ', '.join(str(staffel) for staffel in staffeln)
			sender = ', '.join(sender)

			if not AufnahmeVerzeichnis:
				AufnahmeVerzeichnis = config.plugins.serienRec.savetopath.value

			if not AnzahlAufnahmen:
				AnzahlAufnahmen = config.plugins.serienRec.NoOfRecords.value
			elif AnzahlAufnahmen < 1:
				AnzahlAufnahmen = 1

			if Vorlaufzeit is None:
				Vorlaufzeit = config.plugins.serienRec.margin_before.value
			elif Vorlaufzeit < 0:
				Vorlaufzeit = 0

			if Nachlaufzeit is None:
				Nachlaufzeit = config.plugins.serienRec.margin_after.value
			elif Nachlaufzeit < 0:
				Nachlaufzeit = 0

			markerList.append((ID, Serie, Url, staffeln, sender, AufnahmeVerzeichnis, AnzahlAufnahmen, Vorlaufzeit, Nachlaufzeit, preferredChannel, bool(useAlternativeChannel), SerieAktiviert, Info, fsID))

		return numberOfDeactivatedSeries, markerList
	
	
	def buildList(self, entry):
		(ID, serie, url, staffeln, sender, AufnahmeVerzeichnis, AnzahlAufnahmen, Vorlaufzeit, Nachlaufzeit, preferredChannel, useAlternativeChannel, SerieAktiviert, info, fsID) = entry

		if preferredChannel == 1:
			senderText = "Std."
			if useAlternativeChannel:
				senderText = "%s, Alt." % senderText
		else:
			senderText = "Alt."
			if useAlternativeChannel:
				senderText = "%s, Std." % senderText

		if SerieAktiviert:
			serieColor = None
		else:
			serieColor = parseColor('red').argb()

		foregroundColor = parseColor('foreground').argb()

		senderText = "Sender (%s): %s" % (senderText, sender)
		staffelText = "Staffel: %s" % staffeln
		infoText = "Wdh./Vorl./Nachl.: %s / %s / %s" % (int(AnzahlAufnahmen) - 1, int(Vorlaufzeit), int(Nachlaufzeit))
		folderText = "Dir: %s" % AufnahmeVerzeichnis

		return [entry,
			(eListboxPythonMultiContent.TYPE_TEXT, int(config.plugins.serienRec.markerNameInset.value), 3, (410 + self.columnWidth) * skinFactor, 26 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, serie, serieColor, serieColor),
			(eListboxPythonMultiContent.TYPE_TEXT, (470 + self.columnWidth) * skinFactor, 3, (380 + self.columnWidth) * skinFactor, 26 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, info, serieColor, serieColor),
			(eListboxPythonMultiContent.TYPE_TEXT, 40, 29 * skinFactor, (410 + self.columnWidth) * skinFactor, 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, staffelText, foregroundColor, foregroundColor),
			(eListboxPythonMultiContent.TYPE_TEXT, (470 + self.columnWidth) * skinFactor, 29 * skinFactor, (380 + self.columnWidth) * skinFactor, 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, senderText, foregroundColor, foregroundColor),
			(eListboxPythonMultiContent.TYPE_TEXT, 40, 49 * skinFactor, (410 + self.columnWidth) * skinFactor, 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, infoText, foregroundColor, foregroundColor),
			(eListboxPythonMultiContent.TYPE_TEXT, (470 + self.columnWidth) * skinFactor, 49 * skinFactor, (380 + self.columnWidth) * skinFactor, 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, folderText, foregroundColor, foregroundColor)
			]

	def keyCheck(self):
		if self['menu_list'].getCurrent() is None:
			print("[SerienRecorder] Serien-Marker Tabelle leer.")
			return
		if self.modus == "menu_list":
			if config.plugins.serienRec.tvplaner.value:
				self.session.openWithCallback(self.executeAutoCheck, MessageBox, "Bei 'ja' wird der Suchlauf für TV-Planer Timer gestartet, bei 'nein' wird ein voller Suchlauf durchgeführt.", MessageBox.TYPE_YESNO)
			else:
				self.executeAutoCheck(False)

	def executeAutoCheck(self, withTVPlaner):
		from SerienRecorderAutoCheckScreen import serienRecRunAutoCheckScreen
		self.session.openWithCallback(self.readSerienMarker, serienRecRunAutoCheckScreen, withTVPlaner)

	def keyOK(self):
		if self.modus == "popup_list":	# Staffel
			self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]
			select_staffel = self['popup_list'].getCurrent()[0][0]
			select_mode = self['popup_list'].getCurrent()[0][1]
			select_index = self['popup_list'].getCurrent()[0][2]
			print(select_staffel, select_mode)
			if select_mode == 0:
				select_mode = 1
			else:
				select_mode = 0

			self.staffel_liste[select_index] = list(self.staffel_liste[select_index])
			self.staffel_liste[select_index][1] = select_mode

			if select_mode == 1:
				deselectRange = None
				if select_index == 0:	# 'Manuell'
					# Disable all other special rows
					deselectRange = range(1, 3)
				if select_index == 1:	# Alle
					# Disable 'Manuell' and 'folgende'
					deselectRange = [0, 3]
				if select_index == 2:  # Specials
					# Disable 'Manuell' and 'Alle'
					deselectRange = [0, 1]
				if select_index == 4:  # 0
					# Disable 'Manuell', 'Alle' and 'folgende'
					deselectRange = [0, 1, 3]

				if deselectRange:
					for index in deselectRange:
						self.staffel_liste[index] = list(self.staffel_liste[index])
						self.staffel_liste[index][1] = 0

				if select_index == 0 or select_index == 1 or select_index == 4:  # 'Manuell', 'Alle' or '0'
					for index in range((5 if select_index == 4 else 4), len(self.staffel_liste)):
						# Disable all other season rows
						self.staffel_liste[index] = list(self.staffel_liste[index])
						self.staffel_liste[index][1] = 0

				if select_index >= 3:	# Any season
					for index in [0, 1]:
						# Disable 'Manuell' and 'Alle'
						self.staffel_liste[index] = list(self.staffel_liste[index])
						self.staffel_liste[index][1] = 0

			self.chooseMenuList_popup.setList(map(self.buildList2, self.staffel_liste))
		elif self.modus == "popup_list2":	# Sender
			self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]
			select_sender = self['popup_list'].getCurrent()[0][0]
			select_mode = self['popup_list'].getCurrent()[0][1]
			select_index = self['popup_list'].getCurrent()[0][2]
			print(select_sender, select_mode)
			if select_mode == 0:
				select_mode = 1
			else:
				select_mode = 0
			self.sender_liste[select_index] = list(self.sender_liste[select_index])
			self.sender_liste[select_index][1] = select_mode
			if select_mode == 1:
				if select_index == 0:	# 'Alle'
					# Disable any other channels
					for index in range(1, len(self.sender_liste)):
						# Disable all other season rows
						self.sender_liste[index] = list(self.sender_liste[index])
						self.sender_liste[index][1] = 0
				if select_index >= 1:  	# Any channel
					# Disable 'Alle'
					self.sender_liste[0] = list(self.sender_liste[0])
					self.sender_liste[0][1] = 0
			self.chooseMenuList_popup.setList(map(self.buildList2, self.sender_liste))
		else:
			self.staffelSelect()

	def staffelSelect(self):
		if self.modus == "menu_list":
			if self['menu_list'].getCurrent() is None:
				print("[SerienRecorder] Serien-Marker Tabelle leer.")
				return

			self.modus = "popup_list"
			self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]
			self['popup_list'].show()
			self['popup_bg'].show()
			
			staffeln = ["Manuell", "Alle (inkl. Specials)", "Specials", "Staffeln ab"]
			staffeln.extend(range(config.plugins.serienRec.max_season.value+1))
			mode_list = [0,]*len(staffeln)
			index_list = range(len(staffeln))
			(ID, AlleStaffelnAb, self.AbEpisode, TimerForSpecials) = self.database.getMarkerSeasonSettings(self.selected_serien_wlid)

			if AlleStaffelnAb == -2:		# 'Manuell'
				mode_list[0] = 1
			else:
				if AlleStaffelnAb == 0:		# 'Alle'
					mode_list[1] = 1
				else:
					if bool(TimerForSpecials):
						mode_list[2] = 1
					cStaffelList = self.database.getAllowedSeasons(ID, AlleStaffelnAb)
					if AlleStaffelnAb >= 999999:
						for staffel in cStaffelList:
							mode_list[staffel + 4] = 1
					elif (AlleStaffelnAb > 0) and (AlleStaffelnAb <= (len(staffeln)-4)):
						mode_list[AlleStaffelnAb + 4] = 1
						mode_list[3] = 1
						for staffel in cStaffelList:
							mode_list[staffel + 4] = 1
							if (staffel + 1) == AlleStaffelnAb:
								mode_list[AlleStaffelnAb + 4] = 0
								AlleStaffelnAb = staffel

					if self.AbEpisode > 0:
						mode_list[4] = 1

			if mode_list.count(1) == 0:
				mode_list[0] = 1
			self.staffel_liste = zip(staffeln, mode_list, index_list)
			self.chooseMenuList_popup.setList(map(self.buildList2, self.staffel_liste))

	@staticmethod
	def buildList2(entry):
		(staffel, mode, index) = entry
		if int(mode) == 0:
			imageMode = "%simages/minus.png" % serienRecMainPath
		else:
			imageMode = "%simages/plus.png" % serienRecMainPath

		return [entry,
			(eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 5, 7 * skinFactor, 30 * skinFactor, 17 * skinFactor, loadPNG(imageMode)),
			(eListboxPythonMultiContent.TYPE_TEXT, 40 * skinFactor, 0, 500 * skinFactor, 26 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, str(staffel).zfill(2))
			]

	def keyGreen(self):
		if self.modus == "menu_list":
			if self['menu_list'].getCurrent() is None:
				print("[SerienRecorder] Serien-Marker Tabelle leer.")
				return

			activeChannels = self.database.getActiveChannels()
			if len(activeChannels) != 0:
				self.modus = "popup_list2"
				self['popup_list'].show()
				self['popup_bg'].show()
				self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]

				activeChannels.insert(0, 'Alle')
				mode_list = [0,]*len(activeChannels)
				index_list = range(len(activeChannels))
				channels = self.database.getMarkerChannels(self.selected_serien_wlid, False)
				if len(channels) > 0:
					for channel in channels:
						if channel in activeChannels:
							idx = activeChannels.index(channel)
							mode_list[idx] = 1
				else:
					# No channels assigned to marker => Alle
					mode_list[0] = 1

				self.sender_liste = zip(activeChannels, mode_list, index_list)
				self.chooseMenuList_popup.setList(map(self.buildList2, self.sender_liste))

	def callTimerAdded(self, answer):
		if answer:
			self.changesMade = True
			
	def keyYellow(self):
		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		if serien_name and serien_wlid:
			self.session.openWithCallback(self.callTimerAdded, serienRecSendeTermine, serien_name, serien_wlid, serien_fsid)

	def callDisableAll(self, answer):
		if answer:
			self.database.disableAllMarkers(config.plugins.serienRec.BoxID.value)
			self.readSerienMarker()
		else:
			return

	def callSaveMsg(self, answer):
		if answer:
			(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
			serien_info = self['menu_list'].getCurrent()[0][12]
			self.session.openWithCallback(self.callDelMsg, MessageBox, "Die Timer Einträge für '%s (%s)' auch aus der Datenbank löschen?" % (serien_name, serien_info), MessageBox.TYPE_YESNO, default = False)
		else:
			return

	def callDelMsg(self, answer):
		(serien_name, serien_wlid, serien_fsid) = self.getCurrentSelection()
		self.removeSerienMarker(serien_fsid, serien_name, answer)
		
	def removeSerienMarker(self, serien_fsid, serien_name, answer):
		serien_info = self['menu_list'].getCurrent()[0][12]
		serienRecMarker.doRemoveSerienMarker(serien_fsid, serien_name, serien_info, answer)
		self.changesMade = True
		self['title'].instance.setForegroundColor(parseColor("red"))
		self['title'].setText("Marker für '%s (%s)' wurde gelöscht." % (serien_name, serien_info))
		self.readSerienMarker()	

	@staticmethod
	def doRemoveSerienMarker(serien_fsid, serien_name, serien_info, withTimer):
		from SerienRecorderDatabase import SRDatabase
		from SerienRecorder import serienRecDataBaseFilePath
		database = SRDatabase(serienRecDataBaseFilePath)
		database.removeMarker(serien_fsid, withTimer)
		from SerienRecorderLogWriter import SRLogger
		SRLogger.writeLog("Der Serien-Marker für '%s (%s)' wurde gelöscht" % (serien_name, serien_info), True)

	def keyRed(self):
		if self.modus == "menu_list":
			if self['menu_list'].getCurrent() is None:
				print("[SerienRecorder] Serien-Marker Tabelle leer.")
				return
			else:
				self.selected_serien_wlid = self['menu_list'].getCurrent()[0][2]
				self.database.changeMarkerStatus(self.selected_serien_wlid, config.plugins.serienRec.BoxID.value)
				self.readSerienMarker(self.selected_serien_wlid)
					
	def keyRedLong(self):
		if self.modus == "menu_list":
			if self['menu_list'].getCurrent() is None:
				print("[SerienRecorder] Serien-Marker Tabelle leer.")
				return
			else:
				serien_name = self['menu_list'].getCurrent()[0][1]
				serien_info = self['menu_list'].getCurrent()[0][12]
				if config.plugins.serienRec.confirmOnDelete.value:
					self.session.openWithCallback(self.callSaveMsg, MessageBox, "Den Serien-Marker für '%s (%s)' wirklich löschen?" % (serien_name, serien_info), MessageBox.TYPE_YESNO, default = False)
				else:
					self.session.openWithCallback(self.callDelMsg, MessageBox, "Die Timer Einträge für '%s (%s)' auch aus der Datenbank löschen?" % (serien_name, serien_info), MessageBox.TYPE_YESNO, default = False)

	def disableAll(self):
		if self.modus == "menu_list":
			if self['menu_list'].getCurrent() is None:
				print("[SerienRecorder] Serien-Marker Tabelle leer.")
				return
			else:
				self.session.openWithCallback(self.callDisableAll, MessageBox, "Alle Serien-Marker für diese Box deaktivieren?", MessageBox.TYPE_YESNO, default = False)

	def insertStaffelMarker(self):
		(ID, AlleStaffelnAb, AbEpisode, TimerForSpecials) = self.database.getMarkerSeasonSettings(self.selected_serien_wlid)
		if ID:
			self.database.removeAllMarkerSeasons(self.selected_serien_wlid)
			liste = self.staffel_liste[1:]
			print("[SerienRecorder] insertStaffelMarker")
			print(liste)
			liste = zip(*liste)
			print(liste)
			if 1 in liste[1]:
				TimerForSpecials = 0
				AlleStaffelnAb = 999999
				#staffel_liste = ['Manuell','Alle','Specials','folgende',...]
				for row in self.staffel_liste:
					(staffel, mode, index) = row
					if mode == 1:
						if index == 0:	# 'Manuell'
							AlleStaffelnAb = -2
							AbEpisode = 0
							TimerForSpecials = 0
							break
						if index == 1:		# 'Alle'
							AlleStaffelnAb = 0
							AbEpisode = 0
							TimerForSpecials = 0
							break
						if index == 2:		#'Specials'
							TimerForSpecials = 1
						if index == 3:		#'folgende'
							liste = self.staffel_liste[5:]
							liste.reverse()
							liste = zip(*liste)
							if 1 in liste[1]:
								idx = liste[1].index(1)
								AlleStaffelnAb = liste[0][idx]
						if index > 4:
							if staffel != AlleStaffelnAb:
								self.database.setMarkerSeason(ID, staffel)
					else:
						if index == 4:
							AbEpisode = 0

			else:
				AlleStaffelnAb = -2
				AbEpisode = 0

			if AlleStaffelnAb == -2: # 'Manuell'
				self.session.open(MessageBox, "Mit dieser Einstellung ('Manuell') werden für diesen\nSerien-Marker keine Timer mehr automatisch angelegt!", MessageBox.TYPE_INFO, timeout=10)

		self.database.updateMarkerSeasonsSettings(self.selected_serien_wlid, AlleStaffelnAb, AbEpisode, TimerForSpecials)

		if config.plugins.serienRec.tvplaner_full_check.value:
			config.plugins.serienRec.tvplaner_last_full_check.value = int(0)
			config.plugins.serienRec.tvplaner_last_full_check.save()
			configfile.save()

		self.changesMade = True
		self.readSerienMarker()

	def insertMarkerChannels(self):
		alleSender = 0
		self.database.removeAllMarkerChannels(self.selected_serien_wlid)
		markerID = self.database.getMarkerID(self.selected_serien_wlid)
		liste = self.sender_liste[1:]
		liste = zip(*liste)
		data = []
		if 1 in liste[1]:
			for row in self.sender_liste:
				(sender, mode, index) = row
				if (index == 0) and (mode == 1):		# 'Alle'
					alleSender = 1
					break
				elif mode == 1:		# Sender erlaubt
					data.append((markerID, sender))
			self.database.setMarkerChannels(data)
		else:
			alleSender = 1

		self.database.setAllChannelsToMarker(self.selected_serien_wlid, alleSender)

		self.changesMade = True
		if config.plugins.serienRec.tvplaner_full_check.value:
			config.plugins.serienRec.tvplaner_last_full_check.value = int(0)
			config.plugins.serienRec.tvplaner_last_full_check.save()
			configfile.save()

		self.readSerienMarker()

	def keyBlue(self):
		if self.modus == "menu_list":
			from SerienRecorderTimerListScreen import serienRecTimerListScreen
			self.session.openWithCallback(self.readSerienMarker, serienRecTimerListScreen)

	def searchSeries(self):
		if self.modus == "menu_list":
			self.session.openWithCallback(self.wSearch, NTIVirtualKeyBoard, title = "Serien Titel eingeben:")

	def wSearch(self, serien_name):
		if serien_name:
			print(serien_name)
			self.changesMade = True
			if config.plugins.serienRec.tvplaner_full_check.value:
				config.plugins.serienRec.tvplaner_last_full_check.value = int(0)
				config.plugins.serienRec.tvplaner_last_full_check.save()
				configfile.save()
			from SerienRecorderSearchResultScreen import serienRecSearchResultScreen
			self.session.openWithCallback(self.readSerienMarker, serienRecSearchResultScreen, serien_name)

	def setMenuKeyText(self):
		active = self['menu_list'].getCurrent()[0][11]
		if active:
			self['text_red'].setText("Aus/Löschen")
		else:
			self['text_red'].setText("Ein/Löschen")

	def keyLeft(self):
		if self.modus == "popup_list2":
			self["popup_list"].pageUp()
		else:
			self[self.modus].pageUp()
			self.getCover()
			self.setMenuKeyText()

	def keyRight(self):
		if self.modus == "popup_list2":
			self["popup_list"].pageDown()
		else:
			self[self.modus].pageDown()
			self.getCover()
			self.setMenuKeyText()

	def keyDown(self):
		if self.modus == "popup_list2":
			self["popup_list"].down()
		else:
			self[self.modus].down()
			self.getCover()
			self.setMenuKeyText()

	def keyUp(self):
		if self.modus == "popup_list2":
			self["popup_list"].up()
		else:
			self[self.modus].up()
			self.getCover()
			self.setMenuKeyText()

	def selectEpisode(self, episode):
		if str(episode).isdigit():
			self.database.setMarkerEpisode(self.selected_serien_wlid, episode)
		self.insertStaffelMarker()
			
	def __onClose(self):
		if self.displayTimer:
			self.displayTimer.stop()
			self.displayTimer = None

	def keyExit(self):
		if self.modus == "popup_list" or self.modus == "popup_list2":
			self.keyCancel()
		else:
			print("[SerienRecorder] MarkerScreen exit")
			import SerienRecorderMainScreen
			SerienRecorderMainScreen.showMainScreen = True
			if config.plugins.serienRec.refreshViews.value:
				self.close(self.changesMade)
			else:
				self.close(False)
	
	def keyCancel(self):
		if self.modus == "popup_list":
			self.modus = "menu_list"
			self['popup_list'].hide()
			self['popup_bg'].hide()
			if (self.staffel_liste[0][1] == 0) and (self.staffel_liste[1][1] == 0) and (self.staffel_liste[4][1] == 1):		# nicht ('Manuell' oder 'Alle') und '00'
				self.session.openWithCallback(self.selectEpisode, NTIVirtualKeyBoard, title = "Die Episode eingeben ab der Timer erstellt werden sollen:", text = str(self.AbEpisode))
			else:
				self.insertStaffelMarker()
		elif self.modus == "popup_list2":
			self.modus = "menu_list"
			self['popup_list'].hide()
			self['popup_bg'].hide()
			self.insertMarkerChannels()
		else:
			if config.plugins.serienRec.refreshViews.value:
				self.close(self.changesMade)
			else:
				self.close(False)


class serienRecMarkerSetup(serienRecBaseScreen, Screen, ConfigListScreen, HelpableScreen):
	def __init__(self, session, serien_name, serien_wlid, serien_id, serien_fsid):
		serienRecBaseScreen.__init__(self, session)
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.list = []
		self.session = session
		self.serien_name = serien_name
		self.serien_id = serien_id
		self.serien_wlid = serien_wlid
		self.serien_fsid = serien_fsid
		self.database = SRDatabase(serienRecDataBaseFilePath)
		self.HilfeTexte = {}
		self.fromTime_index = 1
		self.toTime_index = 1
		self.margin_before_index = 1
		self.margin_after_index = 1
		self.NoOfRecords_index = 1

		self["actions"] = HelpableActionMap(self, "SerienRecorderActions", {
			"red": (self.cancel, "Änderungen verwerfen und zurück zur Serien-Marker-Ansicht"),
			"green": (self.save, "Einstellungen speichern und zurück zur Serien-Marker-Ansicht"),
			"blue": (self.resetCover, "Cover zurücksetzen"),
			"cancel": (self.cancel, "Änderungen verwerfen und zurück zur Serien-Marker-Ansicht"),
			"ok": (self.ok, "Fenster für Verzeichnisauswahl öffnen"),
			"up": (self.keyUp, "eine Zeile nach oben"),
			"down": (self.keyDown, "eine Zeile nach unten"),
			"startTeletext": (self.showAbout, "Über dieses Plugin"),
		}, -1)
		self.helpList[0][2].sort()

		self["helpActions"] = ActionMap(["SerienRecorderActions", ], {
			"displayHelp": self.showHelp,
			"displayHelp_long": self.showManual,
		}, 0)

		self.setupSkin()
		if config.plugins.serienRec.showAllButtons.value:
			setMenuTexts(self)

		(AufnahmeVerzeichnis, Staffelverzeichnis, Vorlaufzeit, Nachlaufzeit, AnzahlWiederholungen, AufnahmezeitVon,
		 AufnahmezeitBis, preferredChannel, useAlternativeChannel, vps, excludedWeekdays, tags, addToDatabase, updateFromEPG, skipSeriesServer, autoAdjust, epgSeriesName) = self.database.getMarkerSettings(self.serien_id)

		if not AufnahmeVerzeichnis:
			AufnahmeVerzeichnis = ""
		self.savetopath = ConfigText(default=AufnahmeVerzeichnis, fixed_size=False, visible_width=50)
		self.seasonsubdir = ConfigSelection(choices=[("-1", "Gemäß Setup (dzt. %s)" % str(
			config.plugins.serienRec.seasonsubdir.value).replace("True", "Ja").replace("False", "Nein")), ("0", "Nein"),
													 ("1", "Ja")], default=str(Staffelverzeichnis))

		if str(Vorlaufzeit).isdigit():
			self.margin_before = ConfigInteger(Vorlaufzeit, (0, 999))
			self.enable_margin_before = ConfigYesNo(default=True)
		else:
			self.margin_before = ConfigInteger(config.plugins.serienRec.margin_before.value, (0, 999))
			self.enable_margin_before = ConfigYesNo(default=False)

		if str(Nachlaufzeit).isdigit():
			self.margin_after = ConfigInteger(Nachlaufzeit, (0, 999))
			self.enable_margin_after = ConfigYesNo(default=True)
		else:
			self.margin_after = ConfigInteger(config.plugins.serienRec.margin_after.value, (0, 999))
			self.enable_margin_after = ConfigYesNo(default=False)

		if str(AnzahlWiederholungen).isdigit():
			self.NoOfRecords = ConfigInteger(AnzahlWiederholungen, (1, 9))
			self.enable_NoOfRecords = ConfigYesNo(default=True)
		else:
			self.NoOfRecords = ConfigInteger(config.plugins.serienRec.NoOfRecords.value, (1, 9))
			self.enable_NoOfRecords = ConfigYesNo(default=False)

		if str(AufnahmezeitVon).isdigit():
			self.fromTime = ConfigClock(default=int(AufnahmezeitVon) * 60 + time.timezone)
			self.enable_fromTime = ConfigYesNo(default=True)
		else:
			self.fromTime = ConfigClock(default=((config.plugins.serienRec.globalFromTime.value[0] * 60) +
												 config.plugins.serienRec.globalFromTime.value[1]) * 60 + time.timezone)
			self.enable_fromTime = ConfigYesNo(default=False)

		if str(AufnahmezeitBis).isdigit():
			self.toTime = ConfigClock(default=int(AufnahmezeitBis) * 60 + time.timezone)
			self.enable_toTime = ConfigYesNo(default=True)
		else:
			self.toTime = ConfigClock(default=((config.plugins.serienRec.globalToTime.value[0] * 60) +
											   config.plugins.serienRec.globalToTime.value[1]) * 60 + time.timezone)
			self.enable_toTime = ConfigYesNo(default=False)

		if str(vps).isdigit():
			self.override_vps = ConfigYesNo(default=True)
			self.enable_vps = ConfigYesNo(default=bool(vps & 0x1))
			self.enable_vps_savemode = ConfigYesNo(default=bool(vps & 0x2))
		else:
			self.override_vps = ConfigYesNo(default=False)
			self.enable_vps = ConfigYesNo(default=False)
			self.enable_vps_savemode = ConfigYesNo(default=False)

		if str(addToDatabase).isdigit():
			self.addToDatabase = ConfigYesNo(default=bool(addToDatabase))
		else:
			self.addToDatabase = ConfigYesNo(default=True)

		if str(updateFromEPG).isdigit():
			self.updateFromEPG = ConfigYesNo(default=bool(updateFromEPG))
			self.enable_updateFromEPG = ConfigYesNo(default=True)
		else:
			self.updateFromEPG = ConfigYesNo(default=config.plugins.serienRec.eventid.value)
			self.enable_updateFromEPG = ConfigYesNo(default=False)

		if str(skipSeriesServer).isdigit():
			self.skipSeriesServer = ConfigYesNo(default=bool(skipSeriesServer))
			self.enable_skipSeriesServer = ConfigYesNo(default=True)
		else:
			self.skipSeriesServer = ConfigYesNo(default=config.plugins.serienRec.tvplaner_skipSerienServer.value)
			self.enable_skipSeriesServer = ConfigYesNo(default=False)

		if str(autoAdjust).isdigit():
			self.autoAdjust = ConfigYesNo(default=bool(autoAdjust))
			self.enable_autoAdjust = ConfigYesNo(default=True)
		else:
			self.autoAdjust = ConfigYesNo(default=False)
			self.enable_autoAdjust = ConfigYesNo(default=False)

		self.preferredChannel = ConfigSelection(choices=[("1", "Standard"), ("0", "Alternativ")], default=str(preferredChannel))
		self.useAlternativeChannel = ConfigSelection(choices=[("-1", "Gemäß Setup (dzt. %s)" % str(
			config.plugins.serienRec.useAlternativeChannel.value).replace("True", "Ja").replace("False", "Nein")),
															  ("0", "Nein"), ("1", "Ja")],
													 default=str(useAlternativeChannel))

		# excluded weekdays
		# each weekday is represented by a bit in the database field
		# 0 = Monday to 6 = Sunday, so if all weekdays are excluded we got 1111111 = 127
		if str(excludedWeekdays).isdigit():
			self.enable_excludedWeekdays = ConfigYesNo(default=True)
			self.excludeMonday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 0)))
			self.excludeTuesday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 1)))
			self.excludeWednesday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 2)))
			self.excludeThursday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 3)))
			self.excludeFriday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 4)))
			self.excludeSaturday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 5)))
			self.excludeSunday = ConfigYesNo(default=bool(excludedWeekdays & (1 << 6)))
		else:
			self.enable_excludedWeekdays = ConfigYesNo(default=False)
			self.excludeMonday = ConfigYesNo(default=False)
			self.excludeTuesday = ConfigYesNo(default=False)
			self.excludeWednesday = ConfigYesNo(default=False)
			self.excludeThursday = ConfigYesNo(default=False)
			self.excludeFriday = ConfigYesNo(default=False)
			self.excludeSaturday = ConfigYesNo(default=False)
			self.excludeSunday = ConfigYesNo(default=False)

		# tags
		if tags is None or len(tags) == 0:
			self.serienmarker_tags = []
		else:
			self.serienmarker_tags = pickle.loads(tags)
		self.tags = NoSave(
			ConfigSelection(choices=[len(self.serienmarker_tags) == 0 and "Keine" or ' '.join(self.serienmarker_tags)]))

		# EPG series name
		if epgSeriesName is None:
			epgSeriesName = ""
		self.epgSeriesName = ConfigText(default=epgSeriesName, fixed_size=False, visible_width=50)

		self.changedEntry()
		ConfigListScreen.__init__(self, self.list)
		self.setInfoText()
		self['config_information_text'].setText(self.HilfeTexte[self.savetopath])
		self.onLayoutFinish.append(self.setSkinProperties)

	def callHelpAction(self, *args):
		HelpableScreen.callHelpAction(self, *args)

	def setSkinProperties(self):
		super(self.__class__, self).setSkinProperties()

		self.num_bt_text = ([buttonText_na, buttonText_na, "Abbrechen"],
		                    [buttonText_na, buttonText_na, buttonText_na],
		                    [buttonText_na, buttonText_na, buttonText_na],
		                    [buttonText_na, buttonText_na, "Hilfe"],
		                    [buttonText_na, buttonText_na, buttonText_na])

		self['text_red'].setText("Abbrechen")
		self['text_green'].setText("Speichern")
		if config.plugins.serienRec.downloadCover.value:
			self['text_blue'].setText("Cover auswählen")
		self['text_ok'].setText("Ordner auswählen")

		super(self.__class__, self).startDisplayTimer()

	def setupSkin(self):
		self.skin = None
		InitSkin(self)

		self['config'] = ConfigList([])
		self['config'].show()

		self['config_information'].show()
		self['config_information_text'].show()

		self['title'].setText("Serien-Marker - Einstellungen für '%s':" % self.serien_name)
		if not config.plugins.serienRec.showAllButtons.value:
			self['text_0'].setText("Abbrechen")
			self['text_1'].setText("About")

			self['bt_red'].show()
			self['bt_green'].show()
			if config.plugins.serienRec.downloadCover.value:
				self['bt_blue'].show()
			self['bt_ok'].show()
			self['bt_exit'].show()
			self['bt_text'].show()

			self['text_red'].show()
			self['text_green'].show()
			if config.plugins.serienRec.downloadCover.value:
				self['text_blue'].show()
			self['text_ok'].show()
			self['text_0'].show()
			self['text_1'].show()
			self['text_2'].show()
			self['text_3'].show()
			self['text_4'].show()
		else:
			self['text_0'].hide()
			self['text_1'].hide()
			self['text_2'].hide()
			self['text_3'].hide()
			self['text_4'].hide()
			self['text_5'].hide()
			self['text_6'].hide()
			self['text_7'].hide()
			self['text_8'].hide()
			self['text_9'].hide()

			self['bt_0'].hide()
			self['bt_1'].hide()
			self['bt_2'].hide()
			self['bt_3'].hide()
			self['bt_4'].hide()
			self['bt_5'].hide()
			self['bt_6'].hide()
			self['bt_7'].hide()
			self['bt_8'].hide()
			self['bt_9'].hide()

	def createConfigList(self):
		self.list = []
		self.list.append(getConfigListEntry("Abweichender Speicherort der Aufnahmen:", self.savetopath))
		if self.savetopath.value:
			self.list.append(getConfigListEntry("Staffel-Verzeichnis anlegen:", self.seasonsubdir))
			self.margin_before_index += 1

		self.list.append(getConfigListEntry("Alternativer Serienname im EPG:", self.epgSeriesName))
		self.margin_after_index = self.margin_before_index + 1

		self.list.append(getConfigListEntry("Aktiviere abweichenden Timervorlauf:", self.enable_margin_before))
		if self.enable_margin_before.value:
			self.list.append(getConfigListEntry("      Timervorlauf (in Min.):", self.margin_before))
			self.margin_after_index += 1

		self.NoOfRecords_index = self.margin_after_index + 1

		self.list.append(getConfigListEntry("Aktiviere abweichenden Timernachlauf:", self.enable_margin_after))
		if self.enable_margin_after.value:
			self.list.append(getConfigListEntry("      Timernachlauf (in Min.):", self.margin_after))
			self.NoOfRecords_index += 1

		self.fromTime_index = self.NoOfRecords_index + 1

		self.list.append(getConfigListEntry("Aktiviere abweichende Anzahl der Aufnahmen:", self.enable_NoOfRecords))
		if self.enable_NoOfRecords.value:
			self.list.append(getConfigListEntry("      Anzahl der Aufnahmen:", self.NoOfRecords))
			self.fromTime_index += 1

		self.toTime_index = self.fromTime_index + 1

		self.list.append(getConfigListEntry("Aktiviere abweichende Früheste Zeit für Timer:", self.enable_fromTime))
		if self.enable_fromTime.value:
			self.list.append(getConfigListEntry("      Früheste Zeit für Timer:", self.fromTime))
			self.toTime_index += 1

		self.list.append(getConfigListEntry("Aktiviere abweichende Späteste Zeit für Timer:", self.enable_toTime))
		if self.enable_toTime.value:
			self.list.append(getConfigListEntry("      Späteste Zeit für Timer:", self.toTime))

		if config.plugins.serienRec.eventid.value:
			self.list.append(getConfigListEntry("Aktiviere abweichende Timeraktualisierung aus dem EPG:", self.enable_updateFromEPG))
			if self.enable_updateFromEPG.value:
				self.list.append(getConfigListEntry("      Versuche Timer aus dem EPG zu aktualisieren:", self.updateFromEPG))

		if config.plugins.serienRec.tvplaner.value:
			self.list.append(getConfigListEntry("Aktiviere abweichende Timererstellung nur aus der TV-Planer E-Mail:", self.enable_skipSeriesServer))
			if self.enable_skipSeriesServer.value:
				self.list.append(getConfigListEntry("      Timer nur aus der TV-Planer E-Mail anlegen:", self.skipSeriesServer))

		if VPSPluginAvailable:
			self.list.append(getConfigListEntry("Aktiviere abweichende VPS Einstellungen:", self.override_vps))
			if self.override_vps.value:
				self.list.append(getConfigListEntry("      VPS für diesen Serien-Marker aktivieren:", self.enable_vps))
				if self.enable_vps.value:
					self.list.append(
						getConfigListEntry("            Sicherheitsmodus aktivieren:", self.enable_vps_savemode))

		if isVTI():
			self.list.append(getConfigListEntry("Aktiviere abweichende Aufnahmezeitenanpassung aus den EPG Daten:", self.enable_autoAdjust))
			if self.enable_autoAdjust.value:
				self.list.append(getConfigListEntry("      Aufnahmezeiten automatisch an EPG Daten anpassen:", self.autoAdjust))

		self.list.append(getConfigListEntry("Timer in Timer-Liste speichern:", self.addToDatabase))
		self.list.append(getConfigListEntry("Bevorzugte Sender-Liste:", self.preferredChannel))
		self.list.append(getConfigListEntry("Verwende alternative Sender bei Konflikten:", self.useAlternativeChannel))

		self.list.append(getConfigListEntry("Wochentage von der Timererstellung ausschließen:", self.enable_excludedWeekdays))
		if self.enable_excludedWeekdays.value:
			self.list.append(getConfigListEntry("      Montag:", self.excludeMonday))
			self.list.append(getConfigListEntry("      Dienstag:", self.excludeTuesday))
			self.list.append(getConfigListEntry("      Mittwoch:", self.excludeWednesday))
			self.list.append(getConfigListEntry("      Donnerstag:", self.excludeThursday))
			self.list.append(getConfigListEntry("      Freitag:", self.excludeFriday))
			self.list.append(getConfigListEntry("      Samstag:", self.excludeSaturday))
			self.list.append(getConfigListEntry("      Sonntag:", self.excludeSunday))

		self.list.append(getConfigListEntry("Tags:", self.tags))

	def updateMenuValues(self):
		if self['config'].instance.getCurrentIndex() == self.margin_before_index:
			if self.enable_margin_before.value and not self.margin_before.value:
				self.margin_before.value = config.plugins.serienRec.margin_before.value
		elif self['config'].instance.getCurrentIndex() == self.margin_after_index:
			if self.enable_margin_after.value and not self.margin_after.value:
				self.margin_after.value = config.plugins.serienRec.margin_after.value
		elif self['config'].instance.getCurrentIndex() == self.NoOfRecords_index:
			if self.enable_NoOfRecords.value and not self.NoOfRecords.value:
				self.NoOfRecords.value = config.plugins.serienRec.NoOfRecords.value
		elif self['config'].instance.getCurrentIndex() == self.fromTime_index:
			if self.enable_fromTime.value and not self.fromTime.value:
				self.fromTime.value = config.plugins.serienRec.globalFromTime.value
		elif self['config'].instance.getCurrentIndex() == self.toTime_index:
			if self.enable_toTime.value and not self.toTime.value:
				self.toTime.value = config.plugins.serienRec.globalToTime.value
		self.changedEntry()

	def changedEntry(self):
		self.createConfigList()
		self['config'].setList(self.list)

	def keyLeft(self):
		if self['config'].getCurrent()[1] == self.tags:
			self.chooseTags()
		else:
			ConfigListScreen.keyLeft(self)
			self.updateMenuValues()

	def keyRight(self):
		if self['config'].getCurrent()[1] == self.tags:
			self.chooseTags()
		else:
			ConfigListScreen.keyRight(self)
			self.updateMenuValues()

	def keyDown(self):
		# self.changedEntry()
		if self['config'].instance.getCurrentIndex() >= (len(self.list) - 1):
			self['config'].instance.moveSelectionTo(0)
		else:
			self['config'].instance.moveSelection(self['config'].instance.moveDown)

		# self.setInfoText()
		try:
			text = self.HilfeTexte[self['config'].getCurrent()[1]]
		except:
			text = "Keine Information verfügbar."
		self["config_information_text"].setText(text)

		if self['config'].getCurrent()[1] == self.savetopath:
			self['bt_ok'].show()
			self['text_ok'].show()
		else:
			self['bt_ok'].hide()
			self['text_ok'].hide()

	def keyUp(self):
		# self.changedEntry()
		if self['config'].instance.getCurrentIndex() < 1:
			self['config'].instance.moveSelectionTo(len(self.list) - 1)
		else:
			self['config'].instance.moveSelection(self['config'].instance.moveUp)

		# self.setInfoText()
		try:
			text = self.HilfeTexte[self['config'].getCurrent()[1]]
		except:
			text = "Keine Information verfügbar."
		self["config_information_text"].setText(text)

		if self['config'].getCurrent()[1] == self.savetopath:
			self['bt_ok'].show()
			self['text_ok'].show()
		else:
			self['bt_ok'].hide()
			self['text_ok'].hide()

	def ok(self):
		if self['config'].getCurrent()[1] == self.tags:
			self.chooseTags()
		elif self['config'].getCurrent()[1] == self.epgSeriesName:
			value = self.serien_name if len(self.epgSeriesName.value) == 0 else self.epgSeriesName.value
			self.session.openWithCallback(self.epgSeriesNameEditFinished, NTIVirtualKeyBoard, title="Serien Titel eingeben:", text=value)
		else:
			if self['config'].getCurrent()[1] == self.savetopath:
				if config.plugins.serienRec.seriensubdir.value:
					self.session.openWithCallback(self.openFileSelector, MessageBox,
												  "Hier wird das direkte Aufnahme-Verzeichnis für die Serie ausgewählt, es wird nicht automatisch ein Serien-Ordner angelegt.\n\nMit der blauen Taste kann ein Serien-Ordner manuell angelegt werden.",
												  MessageBox.TYPE_INFO, timeout=15)
				else:
					self.openFileSelector(True)

	def openFileSelector(self, answer):
		if not self.savetopath.value:
			start_dir = config.plugins.serienRec.savetopath.value
		else:
			start_dir = self.savetopath.value

		from SerienRecorderFileListScreen import serienRecFileListScreen
		self.session.openWithCallback(self.selectedMediaFile, serienRecFileListScreen, start_dir, "Aufnahme-Verzeichnis auswählen", self.serien_name)

	def selectedMediaFile(self, res):
		if res is not None:
			if self['config'].instance.getCurrentIndex() == 0:
				print(res)
				self.savetopath.value = res
				self.changedEntry()

	def epgSeriesNameEditFinished(self, res):
		if res is not None:
			self.epgSeriesName.value = res
			self.changedEntry()

	def tagEditFinished(self, res):
		if res is not None:
			self.serienmarker_tags = res
			self.tags.setChoices([len(res) == 0 and "Keine" or ' '.join(res)])

	def chooseTags(self):
		preferredTagEditor = getPreferredTagEditor()
		if preferredTagEditor:
			self.session.openWithCallback(
				self.tagEditFinished,
				preferredTagEditor,
				self.serienmarker_tags
			)

	def resetCover(self):
		if not config.plugins.serienRec.downloadCover.value:
			return

		from SerienRecorderCoverSelectorScreen import CoverSelectorScreen
		self.session.open(CoverSelectorScreen, self.serien_wlid, self.serien_name, self.serien_fsid)

	def setInfoText(self):
		self.HilfeTexte = {
			self.savetopath: "Das Verzeichnis auswählen und/oder erstellen, in dem die Aufnahmen von '%s' gespeichert werden." % self.serien_name,
			self.seasonsubdir: "Bei 'ja' wird für jede Staffel ein eigenes Unterverzeichnis im Serien-Verzeichnis für '%s' (z.B.\n'%sSeason 001') erstellt." % (
				self.serien_name, self.savetopath.value),
			self.epgSeriesName: ("Eingabe des Seriennamens wie er im EPG erscheint.\n\n"
			                     "Manchmal kommt es vor, dass eine Serie bei Wunschliste anders heißt als im EPG (z.B. 'Die 2' vs. 'Die Zwei') das führt dazu, dass der SerienRecorder die Sendung nicht im EPG finden und aktualisieren kann.\n"
			                     "Wenn sich der Serienname unterscheidet, kann der Name hier eingegeben werden, um darüber die Sendung im EPG zu finden."),
			self.enable_margin_before: ("Bei 'ja' kann die Vorlaufzeit für Timer von '%s' eingestellt werden.\n"
										"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Vorlaufzeit.\n"
										"Ist auch beim aufzunehmenden Sender eine Vorlaufzeit eingestellt, so hat der HÖHERE Wert Vorrang.\n"
										"Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.margin_before: ("Die Vorlaufzeit für Timer von '%s' in Minuten.\n"
								 "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Vorlaufzeit.\n"
								 "Ist auch beim aufzunehmenden Sender eine Vorlaufzeit eingestellt, so hat der HÖHERE Wert Vorrang.") % self.serien_name,
			self.enable_margin_after: ("Bei 'ja' kann die Nachlaufzeit für Timer von '%s' eingestellt werden.\n"
									   "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Nachlaufzeit.\n"
									   "Ist auch beim aufzunehmenden Sender eine Nachlaufzeit eingestellt, so hat der HÖHERE Wert Vorrang.\n"
									   "Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.margin_after: ("Die Nachlaufzeit für Timer von '%s' in Minuten.\n"
								"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Nachlaufzeit.\n"
								"Ist auch beim aufzunehmenden Sender eine Nachlaufzeit eingestellt, so hat der HÖHERE Wert Vorrang.") % self.serien_name,
			self.enable_NoOfRecords: (
									 "Bei 'ja' kann die Anzahl der Aufnahmen, die von einer Folge von '%s' gemacht werden sollen, eingestellt werden.\n"
									 "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Anzahl der Aufnahmen.\n"
									 "Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.NoOfRecords: ("Die Anzahl der Aufnahmen, die von einer Folge von '%s' gemacht werden sollen.\n"
							   "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Anzahl der Aufnahmen.") % self.serien_name,
			self.enable_fromTime: (
								  "Bei 'ja' kann die erlaubte Zeitspanne (ab Uhrzeit) für Aufnahmen von '%s' eingestellt werden.\n"
								  "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die früheste Zeit für Timer.\n"
								  "Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.fromTime: ("Die Uhrzeit, ab wann Aufnahmen von '%s' erlaubt sind.\n"
							"Die erlaubte Zeitspanne beginnt um %s:%s Uhr.\n"
							"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die früheste Zeit für Timer.") % (
				               self.serien_name, str(self.fromTime.value[0]).zfill(2), str(self.fromTime.value[1]).zfill(2)),
			self.enable_toTime: (
								"Bei 'ja' kann die erlaubte Zeitspanne (bis Uhrzeit) für Aufnahmen von '%s' eingestellt werden.\n"
								"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die späteste Zeit für Timer.\n"
								"Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.toTime: ("Die Uhrzeit, bis wann Aufnahmen von '%s' erlaubt sind.\n"
						  "Die erlaubte Zeitspanne endet um %s:%s Uhr.\n"
						  "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die späteste Zeit für Timer.") % (
				             self.serien_name, str(self.toTime.value[0]).zfill(2), str(self.toTime.value[1]).zfill(2)),
			self.enable_updateFromEPG: (
								"Bei 'ja' kann für Timer von '%s' eingestellt werden, ob versucht werden soll diesen aus dem EPG zu aktualisieren.\n"
								"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Timeraktualisierung aus dem EPG.\n"
								"Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.updateFromEPG: ("Bei 'ja' wird für Timer von '%s' versucht diese aus dem EPG zu aktualisieren.\n"
						  "Bei 'nein' werden die Timer dieser Serie nicht aus dem EPG aktualisiert.\n"
						  "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Timeraktualisierung aus dem EPG.") % self.serien_name,
			self.enable_skipSeriesServer: (
								"Bei 'ja' kann für Timer von '%s' eingestellt werden, ob Timer nur aus der TV-Planer E-Mail angelegt werden sollen.\n"
								"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Timererstellung nur aus der TV-Planer E-Mail.\n"
								"Bei 'nein' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.skipSeriesServer: ("Bei 'ja' werden Timer von '%s' nur aus der TV-Planer E-Mail erstellt.\n"
						  "Bei 'nein' werden die Timer aus den Daten des SerienServer angelegt.\n"
						  "Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Timererstellung nur aus der TV-Planer E-Mail.") % self.serien_name,
			self.override_vps: ("Bei 'ja' kann VPS für Timer von '%s' eingestellt werden.\n"
								"Diese Einstellung hat Vorrang gegenüber der Einstellung des Senders für VPS.\n"
								"Bei 'nein' gilt die Einstellung vom Sender.") % self.serien_name,
			self.enable_vps: (
							 "Bei 'ja' wird VPS für '%s' aktiviert. Die Aufnahme startet erst, wenn der Sender den Beginn der Ausstrahlung angibt, "
							 "und endet, wenn der Sender das Ende der Ausstrahlung angibt.\n"
							 "Diese Einstellung hat Vorrang gegenüber der Sender Einstellung für VPS.") % self.serien_name,
			self.enable_vps_savemode: (
									  "Bei 'ja' wird der Sicherheitsmodus bei '%s' verwendet. Die programmierten Start- und Endzeiten werden eingehalten.\n"
									  "Die Aufnahme wird nur ggf. früher starten bzw. länger dauern, aber niemals kürzer.\n"
									  "Diese Einstellung hat Vorrang gegenüber der Sender Einstellung für VPS.") % self.serien_name,
			self.enable_autoAdjust: ("Bei 'ja' kann für Timer von '%s' eingestellt werden, ob die Aufnahmezeit automatisch an die EPG Daten angepasst werden soll.\n"
			                        "Diese Einstellung hat Vorrang gegenüber der Einstellung für die automatische Anpassung der Aufnahmezeit an EPG Daten am Sender.\n"
			                         "Bei 'nein' gilt die Einstellung am Sender.") % self.serien_name,
			self.autoAdjust: ("Bei 'ja' wird 'Aufnahmezeit automatisch an EPG Daten anpassen' für Timer von '%s' aktiviert.\n"
			                        "Diese Einstellung hat Vorrang gegenüber der Einstellung für die automatische Anpassung der Aufnahmezeit an EPG Daten am Sender.") % self.serien_name,
			self.addToDatabase: "Bei 'nein' werden für die Timer von '%s' keine Einträge in die Timer-Liste gemacht, sodass die Episoden beliebig oft getimert werden können." % self.serien_name,
			self.preferredChannel: "Auswahl, ob die Standard-Sender oder die alternativen Sender für die Timer von '%s' verwendet werden sollen." % self.serien_name,
			self.useAlternativeChannel: (
										"Mit 'ja' oder 'nein' kann ausgewählt werden, ob versucht werden soll, einen Timer auf dem jeweils anderen Sender (Standard oder alternativ) zu erstellen, "
										"falls der Timer für '%s' auf dem bevorzugten Sender nicht angelegt werden kann.\n"
										"Diese Einstellung hat Vorrang gegenüber der globalen Einstellung für die Verwendung von alternativen Sendern.\n"
										"Bei 'gemäß Setup' gilt die Einstellung vom globalen Setup.") % self.serien_name,
			self.enable_excludedWeekdays: (
										  "Bei 'ja' können bestimmte Wochentage für die Erstellung von Timern für '%s' ausgenommen werden.\n"
										  "Es werden also an diesen Wochentage für diese Serie keine Timer erstellt.\n"
										  "Bei 'nein' werden alle Wochentage berücksichtigt.") % self.serien_name,
			self.tags: ("Verwaltet die Tags für die Timer, die für %s angelegt werden.\n\n"
						"Um diese Option nutzen zu können, muss das Tageditor Plugin installiert sein.") % self.serien_name

		}

		try:
			text = self.HilfeTexte[self['config'].getCurrent()[1]]
		except:
			text = "Keine Information verfügbar."

		self["config_information_text"].setText(text)

	def save(self):
		if not self.enable_margin_before.value:
			Vorlaufzeit = None
		else:
			Vorlaufzeit = self.margin_before.value

		if not self.enable_margin_after.value:
			Nachlaufzeit = None
		else:
			Nachlaufzeit = self.margin_after.value

		if not self.enable_NoOfRecords.value:
			AnzahlWiederholungen = None
		else:
			AnzahlWiederholungen = self.NoOfRecords.value

		if not self.enable_fromTime.value:
			AufnahmezeitVon = None
		else:
			AufnahmezeitVon = (self.fromTime.value[0] * 60) + self.fromTime.value[1]

		if not self.enable_toTime.value:
			AufnahmezeitBis = None
		else:
			AufnahmezeitBis = (self.toTime.value[0] * 60) + self.toTime.value[1]

		if not self.enable_updateFromEPG.value:
			updateFromEPG = None
		else:
			updateFromEPG = self.updateFromEPG.value

		if not self.enable_skipSeriesServer.value:
			skipSeriesServer = None
		else:
			skipSeriesServer = self.skipSeriesServer.value

		if not self.override_vps.value:
			vpsSettings = None
		else:
			vpsSettings = (int(self.enable_vps_savemode.value) << 1) + int(self.enable_vps.value)

		if not self.enable_autoAdjust.value:
			autoAdjust = None
		else:
			autoAdjust = self.autoAdjust.value

		if (not self.savetopath.value) or (self.savetopath.value == ""):
			Staffelverzeichnis = -1
		else:
			Staffelverzeichnis = self.seasonsubdir.value

		if not self.enable_excludedWeekdays.value:
			excludedWeekdays = None
		else:
			excludedWeekdays = 0
			excludedWeekdays |= (self.excludeMonday.value << 0)
			excludedWeekdays |= (self.excludeTuesday.value << 1)
			excludedWeekdays |= (self.excludeWednesday.value << 2)
			excludedWeekdays |= (self.excludeThursday.value << 3)
			excludedWeekdays |= (self.excludeFriday.value << 4)
			excludedWeekdays |= (self.excludeSaturday.value << 5)
			excludedWeekdays |= (self.excludeSunday.value << 6)

		if len(self.serienmarker_tags) == 0:
			tags = ""
		else:
			tags = pickle.dumps(self.serienmarker_tags)

		self.database.setMarkerSettings(self.serien_id, (self.savetopath.value, int(Staffelverzeichnis), Vorlaufzeit, Nachlaufzeit, AnzahlWiederholungen,
		AufnahmezeitVon, AufnahmezeitBis, int(self.preferredChannel.value), int(self.useAlternativeChannel.value),
		vpsSettings, excludedWeekdays, tags, int(self.addToDatabase.value), updateFromEPG, skipSeriesServer, autoAdjust, self.epgSeriesName.value))

		self.close(True)

	def cancel(self):
		self.close(False)


class serienRecSendeTermine(serienRecBaseScreen, Screen, HelpableScreen):
	def __init__(self, session, seriesName, seriesWLID, seriesFSID):
		serienRecBaseScreen.__init__(self, session)
		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		self.database = SRDatabase(serienRecDataBaseFilePath)
		self.session = session
		self.picload = ePicLoad()
		self.seriesName = seriesName
		self.addedEpisodes = self.database.getTimerForSeries(seriesFSID, False)
		self.seriesWLID = seriesWLID
		self.seriesFSID = seriesFSID
		self.skin = None

		self["actions"] = HelpableActionMap(self, "SerienRecorderActions", {
			"ok": (self.keyOK, "umschalten ausgewählter Sendetermin aktiviert/deaktiviert"),
			"cancel": (self.keyCancel, "zurück zur Serien-Marker-Ansicht"),
			"left": (self.keyLeft, "zur vorherigen Seite blättern"),
			"right": (self.keyRight, "zur nächsten Seite blättern"),
			"up": (self.keyUp, "eine Zeile nach oben"),
			"down": (self.keyDown, "eine Zeile nach unten"),
			"red": (self.keyRed, "zurück zur Serien-Marker-Ansicht"),
			"green": (self.keyGreen, "Timer für aktivierte Sendetermine erstellen"),
			"yellow": (self.keyYellow, "umschalten Filter (aktive Sender) aktiviert/deaktiviert"),
			"blue": (self.keyBlue, "Ansicht Timer-Liste öffnen"),
			"menu": (self.recSetup, "Menü für globale Einstellungen öffnen"),
			"startTeletext": (self.wunschliste, "Informationen zur ausgewählten Serie auf Wunschliste anzeigen"),
			"0"	: (self.readLogFile, "Log-File des letzten Suchlaufs anzeigen"),
			"3"		: (self.showProposalDB, "Liste der Serien/Staffel-Starts anzeigen"),
			"4"		: (self.serieInfo, "Informationen zur ausgewählten Serie anzeigen"),
			"6"		: (self.showConflicts, "Liste der Timer-Konflikte anzeigen"),
			"7"		: (self.showWishlist, "Merkzettel (vorgemerkte Folgen) anzeigen"),
		}, -1)
		self.helpList[0][2].sort()

		self["helpActions"] = ActionMap(["SerienRecorderActions" ,], {
			"displayHelp"      : self.showHelp,
			"displayHelp_long" : self.showManual,
		}, 0)

		self.filterMode = 1
		self.title_txt = "aktive Sender"

		self.changesMade = False

		self.setupSkin()

		self.sendetermine_list = []
		self.loading = True

		self.onLayoutFinish.append(self.searchEvents)
		self.onClose.append(self.__onClose)
		self.onLayoutFinish.append(self.setSkinProperties)

	def callHelpAction(self, *args):
		HelpableScreen.callHelpAction(self, *args)

	def setSkinProperties(self):
		super(self.__class__, self).setSkinProperties()

		self['text_red'].setText("Abbrechen")
		self['text_ok'].setText("Auswahl")
		if self.filterMode is 1:
			self['text_yellow'].setText("Filter umschalten")
			self.title_txt = "aktive Sender"
		elif self.filterMode is 2:
			self['text_yellow'].setText("Filter ausschalten")
			self.title_txt = "Marker Sender"
		else:
			self['text_yellow'].setText("Filter einschalten")
			self.title_txt = "alle"
		self['text_blue'].setText("Timer-Liste")

		super(self.__class__, self).startDisplayTimer()

	def setupSkin(self):
		self.skin = None
		InitSkin(self)

		self.chooseMenuList = MenuList([], enableWrapAround=True, content=eListboxPythonMultiContent)
		self.chooseMenuList.l.setFont(0, gFont('Regular', 20 + int(config.plugins.serienRec.listFontsize.value)))
		self.chooseMenuList.l.setItemHeight(int(50 *skinFactor))
		self['menu_list'] = self.chooseMenuList
		self['menu_list'].show()

		self['title'].setText("Lade Web-Sender / STB-Sender...")

		if config.plugins.serienRec.showCover.value:
			self['cover'].show()

		if not config.plugins.serienRec.showAllButtons.value:
			self['bt_red'].show()
			self['bt_green'].show()
			self['bt_ok'].show()
			self['bt_yellow'].show()
			self['bt_blue'].show()
			self['bt_exit'].show()
			self['bt_text'].show()
			self['bt_info'].show()
			self['bt_menu'].show()

			self['text_red'].show()
			self['text_green'].show()
			self['text_ok'].show()
			self['text_yellow'].show()
			self['text_blue'].show()
			self['text_0'].show()
			self['text_1'].show()
			self['text_2'].show()
			self['text_3'].show()
			self['text_4'].show()

	def serieInfo(self):
		if self.loading:
			return

		if self.seriesWLID:
			from SerienRecorderSeriesInfoScreen import serienRecShowInfo
			self.session.open(serienRecShowInfo, self.seriesName, self.seriesWLID, self.seriesFSID)

	# self.session.open(MessageBox, "Diese Funktion steht in dieser Version noch nicht zur Verfügung!",
		#				  MessageBox.TYPE_INFO, timeout=10)

	def wunschliste(self):
		serien_id = self.seriesWLID
		super(self.__class__, self).wunschliste(serien_id)

	def setupClose(self, result):
		if not result[2]:
			self.close()
		else:
			if result[0]:
				if config.plugins.serienRec.timeUpdate.value:
					serienRecCheckForRecording(self.session, False, False)

			if result[1]:
				self.searchEvents()

	def searchEvents(self, result=None):
		self['title'].setText("Suche ' %s '" % self.seriesName)
		print("[SerienRecorder] suche ' %s '" % self.seriesName)
		print(self.seriesWLID)

		transmissions = None
		if self.seriesWLID:

			if self.seriesWLID != 0:
				print(self.seriesWLID)
				getCover(self, self.seriesName, self.seriesWLID, self.seriesFSID)

				if self.filterMode is 0:
					webChannels = []
				elif self.filterMode is 1:
					webChannels = self.database.getActiveChannels()
				else:
					webChannels = self.database.getMarkerChannels(self.seriesWLID)

				try:
					transmissions = SeriesServer().doGetTransmissions(self.seriesWLID, 0, webChannels)
				except:
					transmissions = None
			else:
				transmissions = None

		self.resultsEvents(transmissions)

	def resultsEvents(self, transmissions):
		if transmissions is None:
			self['title'].setText("Fehler beim Abrufen der Termine für ' %s '" % self.seriesName)
			return
		self.sendetermine_list = []

		# Update added list in case of made changes
		if self.changesMade:
			self.addedEpisodes = self.database.getTimerForSeries(self.seriesFSID, False)

		# build unique dir list by season
		dirList = {}
		# build unique margins
		marginList = {}

		SerieStaffel = None
		AbEpisode = None
		try:
			(serienTitle, SerieUrl, SerieStaffel, SerieSender, AbEpisode, AnzahlAufnahmen, SerieEnabled, excludedWeekdays, skipSeriesServer, markerType, fsID) = self.database.getMarkers(config.plugins.serienRec.BoxID.value, config.plugins.serienRec.NoOfRecords.value, [self.seriesFSID])[0]
		except:
			SRLogger.writeLog("Fehler beim Filtern nach Staffel", True)

		for serien_name, sender, startzeit, endzeit, staffel, episode, title, status in transmissions:
			seasonAllowed = True
			if config.plugins.serienRec.seasonFilter.value:
				seasonAllowed = self.isSeasonAllowed(staffel, episode, SerieStaffel, AbEpisode)

			if seasonAllowed:
				seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))

				bereits_vorhanden = False
				if config.plugins.serienRec.sucheAufnahme.value:
					if not staffel in dirList:
						dirList[staffel] = getDirname(self.database, serien_name, self.seriesFSID, staffel)

					(dirname, dirname_serie) = dirList[staffel]
					if str(episode).isdigit():
						if int(episode) == 0:
							bereits_vorhanden = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString, serien_name, True, title) and True or False
						else:
							bereits_vorhanden = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString, serien_name, True) and True or False
					else:
						bereits_vorhanden = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString, serien_name, True) and True or False

				if bereits_vorhanden:
					addedType = 1
				else:
					if not sender in marginList:
						marginList[sender] = self.database.getMargins(self.seriesFSID, sender, config.plugins.serienRec.margin_before.value, config.plugins.serienRec.margin_after.value)

					(margin_before, margin_after) = marginList[sender]

					# check 2 (im timer file)
					start_unixtime = startzeit - (int(margin_before) * 60)

					if self.isTimerAdded(self.addedEpisodes, sender, staffel, episode, int(start_unixtime), title):
						addedType = 2
					elif self.isAlreadyAdded(self.addedEpisodes, staffel, episode, title):
						addedType = 3
					else:
						addedType = 0

				if not config.plugins.serienRec.timerFilter.value or config.plugins.serienRec.timerFilter.value and addedType == 0:
					self.sendetermine_list.append([serien_name, sender, startzeit, endzeit, staffel, episode, title, status, addedType])

		if len(self.sendetermine_list):
			self['text_green'].setText("Timer erstellen")

		self.chooseMenuList.setList(map(self.buildList_termine, self.sendetermine_list))
		self.loading = False
		self['title'].setText("%s Sendetermine für ' %s ' gefunden. (%s)" %
		                      (str(len(self.sendetermine_list)), self.seriesName, self.title_txt))

	@staticmethod
	def buildList_termine(entry):
		(serien_name, sender, start, end, staffel, episode, title, status, addedType) = entry

		# addedType: 0 = None, 1 = on HDD, 2 = Timer available, 3 = in DB
		seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))

		WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
		transmissionTime = time.localtime(start)
		datum = time.strftime(WEEKDAYS[transmissionTime.tm_wday] + ", %d.%m.%Y", transmissionTime)
		startTime = time.strftime("%H:%M", transmissionTime)

		imageMinus = "%simages/minus.png" % serienRecMainPath
		imagePlus = "%simages/plus.png" % serienRecMainPath
		imageNone = "%simages/black.png" % serienRecMainPath

		if int(status) == 0:
			leftImage = imageMinus
		else:
			leftImage = imagePlus

		imageHDD = imageNone
		imageTimer = imageNone
		if addedType == 1:
			titleColor = None
			imageHDD = "%simages/hdd_icon.png" % serienRecMainPath
		elif addedType == 2:
			titleColor = parseColor('blue').argb()
			imageTimer = "%simages/timer.png" % serienRecMainPath
		elif addedType == 3:
			titleColor = parseColor('green').argb()
		else:
			titleColor = parseColor('red').argb()

		foregroundColor = parseColor('foreground').argb()

		return [entry,
				(eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 5, 15 * skinFactor, 16 * skinFactor, 16 * skinFactor,
				 loadPNG(leftImage)),
				(eListboxPythonMultiContent.TYPE_TEXT, 40 * skinFactor, 3, 240 * skinFactor, 26 * skinFactor, 0,
				 RT_HALIGN_LEFT | RT_VALIGN_CENTER, sender, foregroundColor, foregroundColor),
				(eListboxPythonMultiContent.TYPE_TEXT, 40 * skinFactor, 29 * skinFactor, 230 * skinFactor,
				 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, "%s - %s" % (datum, startTime)),
				(eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 265 * skinFactor, 7 * skinFactor, 30 * skinFactor,
				 22 * skinFactor, loadPNG(imageTimer)),
				(eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 265 * skinFactor, 30 * skinFactor, 30 * skinFactor,
				 22 * skinFactor, loadPNG(imageHDD)),
				(eListboxPythonMultiContent.TYPE_TEXT, 300 * skinFactor, 3, 500 * skinFactor, 26 * skinFactor, 0,
				 RT_HALIGN_LEFT | RT_VALIGN_CENTER, serien_name, foregroundColor, foregroundColor),
				(eListboxPythonMultiContent.TYPE_TEXT, 300 * skinFactor, 29 * skinFactor, 498 * skinFactor,
				 18 * skinFactor, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, "%s - %s" % (seasonEpisodeString, title),
				 titleColor, titleColor)
				]

	@staticmethod
	def isAlreadyAdded(addedEpisodes, season, episode, title=None):
		result = False
		# Title is only relevant if season and episode is 0
		# this happen when Wunschliste has no episode and season information
		seasonEpisodeString = "S%sE%s" % (str(season).zfill(2), str(episode).zfill(2))
		if seasonEpisodeString != "S00E00":
			title = None
		if not title:
			for addedEpisode in addedEpisodes:
				if addedEpisode[0] == season and addedEpisode[1] == episode:
					result = True
					break
		else:
			for addedEpisode in addedEpisodes:
				if addedEpisode[0] == season and addedEpisode[1] == episode and addedEpisode[2] == title:
					result = True
					break

		return result

	@staticmethod
	def isTimerAdded(addedEpisodes, sender, season, episode, start_unixtime, title=None):
		result = False
		if not title:
			for addedEpisode in addedEpisodes:
				if addedEpisode[0] == season and addedEpisode[1] == episode and addedEpisode[
					3] == sender.lower() and int(start_unixtime) - (int(STBHelpers.getEPGTimeSpan()) * 60) <= \
						addedEpisode[4] <= int(start_unixtime) + (int(STBHelpers.getEPGTimeSpan()) * 60):
					result = True
					break
		else:
			for addedEpisode in addedEpisodes:
				if ((addedEpisode[0] == season and addedEpisode[1] == episode) or addedEpisode[2] == title) and \
						addedEpisode[3] == sender.lower() and int(start_unixtime) - (
						int(STBHelpers.getEPGTimeSpan()) * 60) <= addedEpisode[4] <= int(start_unixtime) + (
						int(STBHelpers.getEPGTimeSpan()) * 60):
					result = True
					break

		return result

	def countSelectedTransmissionForTimerCreation(self):
		result = 0
		for serien_name, sender, start_unixtime, end_unixtime, staffel, episode, title, status, addedType in self.sendetermine_list:
			if int(status) == 1:
				result += 1

		return result

	def getTimes(self):
		changesMade = False
		if len(self.sendetermine_list) != 0 and self.countSelectedTransmissionForTimerCreation() != 0:
			(activatedTimer, deactivatedTimer) = serienRecSendeTermine.prepareTimer(self.database, self.filterMode, self.seriesWLID, self.seriesFSID, self.sendetermine_list)

			# self.session.open(serienRecRunAutoCheck, False)
			from SerienRecorderLogScreen import serienRecReadLog
			self.session.open(serienRecReadLog)
			if activatedTimer > 0 or deactivatedTimer > 0:
				changesMade = True

		else:
			self['title'].setText("Keine Sendetermine ausgewählt.")
			print("[SerienRecorder] keine Sendetermine ausgewählt.")

		return changesMade

	@staticmethod
	def createTimer(database, filterMode, wlid, fsid, params, force=True):
		activatedTimer = 0
		deactivatedTimer = 0

		if not force:
			return False, activatedTimer, deactivatedTimer
		else:
			(serien_name, sender, start_unixtime, margin_before, margin_after, end_unixtime, label_serie,
			 staffel, episode, title, dirname, preferredChannel, useAlternativeChannel, vpsSettings, tags,
			 addToDatabase, autoAdjust, epgSeriesName) = params
			# check sender
			(webChannel, stbChannel, stbRef, altstbChannel, altstbRef, status) = database.getChannelInfo(sender, wlid, filterMode)

			TimerOK = False
			if stbChannel == "":
				SRLogger.writeLog("' %s ' - Kein STB-Kanal gefunden -> ' %s '" % (serien_name, webChannel))
			elif int(status) == 0:
				SRLogger.writeLog("' %s ' - STB-Kanel deaktiviert -> ' %s '" % (serien_name, webChannel))
			else:
				from SerienRecorderTimer import serienRecTimer, serienRecBoxTimer
				timer = serienRecTimer()
				timer_name = serienRecTimer.getTimerName(serien_name, staffel, episode, title, 0)

				if preferredChannel == 1:
					timer_stbRef = stbRef
					timer_altstbRef = altstbRef
				else:
					timer_stbRef = altstbRef
					timer_altstbRef = stbRef

				# try to get eventID (eit) from epgCache
				eit, start_unixtime_eit, end_unixtime_eit = STBHelpers.getStartEndTimeFromEPG(start_unixtime,
				                                                                              end_unixtime,
				                                                                              margin_before,
				                                                                              margin_after, serien_name,
				                                                                              timer_stbRef)
				if eit is 0 and len(epgSeriesName) > 0 and epgSeriesName != serien_name:
					eit, start_unixtime_eit, end_unixtime_eit = STBHelpers.getStartEndTimeFromEPG(start_unixtime,
					                                                                              end_unixtime,
					                                                                              margin_before,
					                                                                              margin_after, epgSeriesName,
					                                                                              timer_stbRef)
				if eit > 0:
					# Adjust the EPG start/end time with margins
					start_unixtime_eit = int(start_unixtime_eit) - (int(margin_before) * 60)
					end_unixtime_eit = int(end_unixtime_eit) + (int(margin_after) * 60)

				updateFromEPG = database.getUpdateFromEPG(fsid)
				if updateFromEPG is False:
					start_unixtime_eit = start_unixtime
					end_unixtime_eit = end_unixtime

				seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))
				konflikt = ""

				# versuche timer anzulegen
				result = serienRecBoxTimer.addTimer(timer_stbRef, str(start_unixtime_eit), str(end_unixtime_eit),
				                                    timer_name, "%s - %s" % (seasonEpisodeString, title), eit,
				                                    False, dirname, vpsSettings, tags, autoAdjust, None)
				if result["result"]:
					timer.addTimerToDB(serien_name, wlid, fsid, staffel, episode, title, str(start_unixtime_eit), timer_stbRef, webChannel, eit, addToDatabase)
					activatedTimer += 1
					TimerOK = True
				else:
					konflikt = result["message"]

				if not TimerOK and useAlternativeChannel:
					# try to get eventID (eit) from epgCache
					alt_eit, alt_start_unixtime_eit, alt_end_unixtime_eit = STBHelpers.getStartEndTimeFromEPG(
						start_unixtime, end_unixtime, margin_before, margin_after, serien_name, timer_altstbRef)

					if alt_eit is 0 and len(epgSeriesName) > 0 and epgSeriesName != serien_name:
						alt_eit, alt_start_unixtime_eit, alt_end_unixtime_eit = STBHelpers.getStartEndTimeFromEPG(
							start_unixtime, end_unixtime, margin_before, margin_after, epgSeriesName, timer_altstbRef)

					updateFromEPG = database.getUpdateFromEPG(fsid)
					if updateFromEPG is False:
						alt_start_unixtime_eit = start_unixtime
						alt_end_unixtime_eit = end_unixtime

					alt_start_unixtime_eit = int(alt_start_unixtime_eit) - (int(margin_before) * 60)
					alt_end_unixtime_eit = int(alt_end_unixtime_eit) + (int(margin_after) * 60)

					# versuche timer anzulegen
					result = serienRecBoxTimer.addTimer(timer_altstbRef, str(alt_start_unixtime_eit),
					                                    str(alt_end_unixtime_eit), timer_name,
					                                    "%s - %s" % (seasonEpisodeString, title), alt_eit, False,
					                                    dirname, vpsSettings, tags, autoAdjust, None)
					if result["result"]:
						konflikt = None
						timer.addTimerToDB(serien_name, wlid, fsid, staffel, episode, title, str(alt_start_unixtime_eit), timer_altstbRef, webChannel, alt_eit, addToDatabase)
						activatedTimer += 1
						TimerOK = True
					else:
						konflikt = result["message"]

				if (not TimerOK) and konflikt:
					SRLogger.writeLog("' %s ' - ACHTUNG! -> %s" % (label_serie, konflikt), True)
					dbMessage = result["message"].replace("In Konflikt stehende Timer vorhanden!", "").strip()

					result = serienRecBoxTimer.addTimer(timer_stbRef, str(start_unixtime_eit), str(end_unixtime_eit),
					                                    timer_name, "%s - %s" % (seasonEpisodeString, title), eit, True,
					                                    dirname, vpsSettings, tags, autoAdjust, None)
					if result["result"]:
						timer.addTimerToDB(serien_name, wlid, fsid, staffel, episode, title, str(start_unixtime_eit), timer_stbRef, webChannel, eit, addToDatabase, False)
						deactivatedTimer += 1
						TimerOK = True
						database.addTimerConflict(dbMessage, start_unixtime_eit, webChannel)

			return TimerOK, activatedTimer, deactivatedTimer

	@staticmethod
	def prepareTimer(database, filterMode, wlid, fsid, sendetermine):

		activatedTimer = 0
		deactivatedTimer = 0

		lt = time.localtime()
		uhrzeit = time.strftime("%d.%m.%Y - %H:%M:%S", lt)
		print("\n---------' Manuelle Timererstellung aus Sendeterminen um %s '---------" % uhrzeit)
		SRLogger.writeLog("\n---------' Manuelle Timererstellung aus Sendeterminen um %s '---------" % uhrzeit, True)
		for serien_name, sender, start_unixtime, end_unixtime, staffel, episode, title, status, addedType in sendetermine:
			if int(status) == 1:
				# initialize strings
				seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))
				label_serie = "%s - %s - %s" % (serien_name, seasonEpisodeString, title)

				# setze die vorlauf/nachlauf-zeit
				(margin_before, margin_after) = database.getMargins(fsid, sender,
				                                                         config.plugins.serienRec.margin_before.value,
				                                                         config.plugins.serienRec.margin_after.value)
				start_unixtime = int(start_unixtime) - (int(margin_before) * 60)
				end_unixtime = int(end_unixtime) + (int(margin_after) * 60)

				# get VPS settings for channel
				vpsSettings = database.getVPS(fsid, sender)

				# get tags from marker
				tags = database.getTags(wlid)

				# get addToDatabase for marker
				addToDatabase = database.getAddToDatabase(wlid)

				# get autoAdjust for marker
				autoAdjust = database.getAutoAdjust(wlid, sender)

				# get alternative epg series name
				epgSeriesName = database.getMarkerEPGName(fsid)

				(dirname, dirname_serie) = getDirname(database, serien_name, fsid, staffel)

				# überprüft anhand des Seriennamen, Season, Episode ob die serie bereits auf der HDD existiert
				if str(episode).isdigit():
					if int(episode) == 0:
						bereits_vorhanden = database.getNumberOfTimers(fsid, staffel, str(int(episode)),
						                                                    title, searchOnlyActiveTimers=True)
						bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString,
						                                                     serien_name, False, title)
					else:
						bereits_vorhanden = database.getNumberOfTimers(fsid, staffel, str(int(episode)),
						                                                    searchOnlyActiveTimers=True)
						bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString,
						                                                     serien_name, False)
				else:
					bereits_vorhanden = database.getNumberOfTimers(fsid, staffel, episode,
					                                                    searchOnlyActiveTimers=True)
					bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, seasonEpisodeString, serien_name,
					                                                     False)

				(NoOfRecords, preferredChannel, useAlternativeChannel) = database.getPreferredMarkerChannels(
					wlid, config.plugins.serienRec.useAlternativeChannel.value,
					config.plugins.serienRec.NoOfRecords.value)

				params = (serien_name, sender, start_unixtime, margin_before, margin_after, end_unixtime,
				          label_serie, staffel, episode, title, dirname, preferredChannel,
				          bool(useAlternativeChannel), vpsSettings, tags, addToDatabase, autoAdjust, epgSeriesName)
				if (bereits_vorhanden < NoOfRecords) and (bereits_vorhanden_HDD < NoOfRecords):
					(TimerDone, onTimer, offTimer) = serienRecSendeTermine.createTimer(database, filterMode, wlid, fsid, params)
				else:
					SRLogger.writeLog("' %s ' -> Staffel/Episode bereits vorhanden ' %s '" % (
						serien_name, seasonEpisodeString))
					(TimerDone, onTimer, offTimer) = serienRecSendeTermine.createTimer(database, filterMode, wlid, fsid, params, config.plugins.serienRec.forceManualRecording.value)

				activatedTimer += onTimer
				deactivatedTimer += offTimer
				if TimerDone:
					# erstellt das serien verzeichnis und kopiert das Cover in das Verzeichnis
					STBHelpers.createDirectory(fsid, 0, dirname, dirname_serie)

		SRLogger.writeLog("Es wurde(n) %s Timer erstellt." % str(activatedTimer), True)
		print("[SerienRecorder] Es wurde(n) %s Timer erstellt." % str(activatedTimer))
		if deactivatedTimer > 0:
			SRLogger.writeLog("%s Timer wurde(n) wegen Konflikten deaktiviert erstellt!" % str(deactivatedTimer), True)
			print("[SerienRecorder] %s Timer wurde(n) wegen Konflikten deaktiviert erstellt!" % str(deactivatedTimer))
		SRLogger.writeLog("---------' Manuelle Timererstellung aus Sendeterminen beendet '---------", True)
		print("---------' Manuelle Timererstellung aus Sendeterminen beendet '---------")

		return activatedTimer, deactivatedTimer

	def isSeasonAllowed(self, season, episode, markerSeasons, fromEpisode):
		if not markerSeasons and not fromEpisode:
			return True

		allowed = False
		if -2 in markerSeasons:  # 'Manuell'
			allowed = False
		elif (-1 in markerSeasons) and (0 in markerSeasons):  # 'Alle'
			allowed = True
		elif str(season).isdigit():
			if int(season) == 0:
				if str(episode).isdigit():
					if int(episode) < int(fromEpisode):
						allowed = False
					else:
						allowed = True
			elif int(season) in markerSeasons:
				allowed = True
			elif -1 in markerSeasons:  # 'folgende'
				if int(season) >= max(markerSeasons):
					allowed = True
		elif self.database.getSpecialsAllowed(self.seriesWLID):
			allowed = True

		return allowed

	def keyOK(self):
		if self.loading or self['menu_list'].getCurrent() is None:
			return

		sindex = self['menu_list'].getSelectedIndex()
		if len(self.sendetermine_list) != 0:
			if int(self.sendetermine_list[sindex][7]) == 0:
				self.sendetermine_list[sindex][7] = "1"
			else:
				self.sendetermine_list[sindex][7] = "0"
			self.chooseMenuList.setList(map(self.buildList_termine, self.sendetermine_list))

	def keyLeft(self):
		self['menu_list'].pageUp()

	def keyRight(self):
		self['menu_list'].pageDown()

	def keyDown(self):
		self['menu_list'].down()

	def keyUp(self):
		self['menu_list'].up()

	def keyRed(self):
		if config.plugins.serienRec.refreshViews.value:
			self.close(self.changesMade)
		else:
			self.close(False)

	def keyGreen(self):
		self.changesMade = self.getTimes()
		if self.changesMade:
			self.searchEvents()

	def keyYellow(self):
		self.sendetermine_list = []
		self.loading = True
		self.chooseMenuList.setList(map(self.buildList_termine, self.sendetermine_list))

		if self.filterMode is 0:
			self.filterMode = 1
			self['text_yellow'].setText("Filter umschalten")
			self.title_txt = "aktive Sender"
		elif self.filterMode is 1:
			self.filterMode = 2
			self['text_yellow'].setText("Filter ausschalten")
			self.title_txt = "Marker Sender"
		else:
			self.filterMode = 0
			self['text_yellow'].setText("Filter einschalten")
			self.title_txt = "alle"

		print("[SerienRecorder] suche ' %s '" % self.seriesName)
		self['title'].setText("Suche ' %s '" % self.seriesName)
		print(self.seriesWLID)

		if self.filterMode is 0:
			webChannels = []
		elif self.filterMode is 1:
			webChannels = self.database.getActiveChannels()
		else:
			webChannels = self.database.getMarkerChannels(self.seriesWLID)

		try:
			transmissions = SeriesServer().doGetTransmissions(self.seriesWLID, 0, webChannels)
		except:
			transmissions = None
		self.resultsEvents(transmissions)

	def keyBlue(self):
		from SerienRecorderTimerListScreen import serienRecTimerListScreen
		self.session.openWithCallback(self.searchEvents, serienRecTimerListScreen)

	def __onClose(self):
		if self.displayTimer:
			self.displayTimer.stop()
			self.displayTimer = None

	def keyCancel(self):
		if config.plugins.serienRec.refreshViews.value:
			self.close(self.changesMade)
		else:
			self.close(False)
