!macro qxStopBackground
  IfFileExists "$INSTDIR\resources\workbench\desktop-runner\stop-installed.cjs" 0 qx_stop_done
  nsExec::ExecToStack '"$INSTDIR\resources\workbench\runtime\node.exe" "$INSTDIR\resources\workbench\desktop-runner\stop-installed.cjs"'
  Pop $0
  Pop $1
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "工作台后台未退出，请关闭工作台后重试。"
    Abort
  ${EndIf}
  qx_stop_done:
!macroend
!macro customInit
  ${If} ${isForAllUsers}
  ${OrIf} $hasPerMachineInstallation == "1"
    MessageBox MB_OK|MB_ICONEXCLAMATION "此安装包用于当前 Windows 用户。检测到其他安装方式，原程序保持不变，请联系支持。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  !insertmacro setInstallModePerUser
  !ifmacrodef qxRecoverInterruptedInstall
    !insertmacro qxRecoverInterruptedInstall
  !endif
  !insertmacro qxStopBackground
!macroend
!macro customInstallMode
  !ifndef BUILD_UNINSTALLER
    StrCpy $isForceCurrentInstall "1"
  !endif
!macroend
!macro customUnInit
  !insertmacro qxStopBackground
!macroend
