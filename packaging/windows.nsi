Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

Name "Atom Lens"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\Atom Lens"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "${RELEASE_VERSION}.0"
VIAddVersionKey "ProductName" "Atom Lens"
VIAddVersionKey "FileDescription" "Atom Lens Windows Setup"
VIAddVersionKey "FileVersion" "${RELEASE_VERSION}"
VIAddVersionKey "LegalCopyright" "Atom Lens contributors (MIT)"

!define APP_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\AtomLens"
!define MUI_ICON "${APP_DIRECTORY}/resources/atom-lens/AtomLens.ico"
!define MUI_UNICON "${APP_DIRECTORY}/resources/atom-lens/AtomLens.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\app\AtomLens.exe"

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "SimpChinese"

LangString WrongSystem ${LANG_ENGLISH} "Atom Lens requires Windows 10 or 11 (64-bit)."
LangString WrongSystem ${LANG_SIMPCHINESE} "Atom Lens 需要 64 位 Windows 10 或 Windows 11。"
LangString AppInUse ${LANG_ENGLISH} "Close Atom Lens and try again."
LangString AppInUse ${LANG_SIMPCHINESE} "请关闭 Atom Lens 后重试。"
LangString ExistingFolder ${LANG_ENGLISH} "The Atom Lens directory is already in use by another application."
LangString ExistingFolder ${LANG_SIMPCHINESE} "Atom Lens 安装目录已被其他应用占用。"
LangString CopyFailed ${LANG_ENGLISH} "Atom Lens could not be installed. Check the available space and try again."
LangString CopyFailed ${LANG_SIMPCHINESE} "Atom Lens 安装失败。请检查磁盘空间后重试。"

Function .onInit
  ${IfNot} ${RunningX64}
  ${OrIfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "$(WrongSystem)"
    Abort
  ${EndIf}
FunctionEnd

Section "Atom Lens"
  SetShellVarContext current
  IfFileExists "$INSTDIR\Uninstall.exe" recover
  IfFileExists "$INSTDIR\app\*.*" 0 extract
  MessageBox MB_ICONSTOP "$(ExistingFolder)"
  Abort
recover:
  IfFileExists "$INSTDIR\app-previous\*.*" 0 extract
  IfFileExists "$INSTDIR\app\*.*" discardBackup
  ClearErrors
  Rename "$INSTDIR\app-previous" "$INSTDIR\app"
  IfErrors installError extract
discardBackup:
  RMDir /r "$INSTDIR\app-previous"
extract:
  SetOutPath "$INSTDIR"
  ClearErrors
  GetTempFileName $0 "$INSTDIR"
  IfErrors installError
  Delete "$0"
  ClearErrors
  SetOutPath "$0"
  IfErrors installError
  File /r "${APP_DIRECTORY}/*"
  IfErrors installError
  SetOutPath "$INSTDIR"
  IfFileExists "$INSTDIR\app\*.*" 0 publish
  ClearErrors
  Rename "$INSTDIR\app" "$INSTDIR\app-previous"
  IfErrors inUse
publish:
  ClearErrors
  Rename "$0" "$INSTDIR\app"
  IfErrors restore
  SetOutPath "$INSTDIR\app"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\Atom Lens.lnk" "$INSTDIR\app\AtomLens.exe" "" "$INSTDIR\app\resources\atom-lens\AtomLens.ico"
  WriteRegStr HKCU "${APP_KEY}" "DisplayName" "Atom Lens"
  WriteRegStr HKCU "${APP_KEY}" "DisplayVersion" "${RELEASE_VERSION}"
  WriteRegStr HKCU "${APP_KEY}" "DisplayIcon" "$INSTDIR\app\resources\atom-lens\AtomLens.ico"
  WriteRegStr HKCU "${APP_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegDWORD HKCU "${APP_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_KEY}" "NoRepair" 1
  RMDir /r "$INSTDIR\app-previous"
  Goto done
restore:
  IfFileExists "$INSTDIR\app-previous\*.*" 0 installError
  Rename "$INSTDIR\app-previous" "$INSTDIR\app"
installError:
  SetOutPath "$INSTDIR"
  StrCmp $0 "" +2
  RMDir /r "$0"
  MessageBox MB_ICONSTOP "$(CopyFailed)"
  Abort
inUse:
  RMDir /r "$0"
  MessageBox MB_ICONSTOP "$(AppInUse)"
  Abort
done:
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  ClearErrors
  Delete "$INSTDIR\app\AtomLens.exe"
  IfErrors 0 remove
  MessageBox MB_ICONSTOP "$(AppInUse)"
  Abort
remove:
  Delete "$SMPROGRAMS\Atom Lens.lnk"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\app-previous"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${APP_KEY}"
SectionEnd
