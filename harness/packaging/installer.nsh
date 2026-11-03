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
  !insertmacro qxStopBackground
!macroend
!macro customUnInit
  !insertmacro qxStopBackground
!macroend
