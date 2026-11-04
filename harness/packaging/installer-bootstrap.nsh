!ifndef BUILD_UNINSTALLER
Var qxNodeReady

!macro qxTryBootstrapNode SOURCE
  ${If} $qxNodeReady != "1"
  ${AndIf} ${FileExists} "${SOURCE}"
    ClearErrors
    CopyFiles /SILENT "${SOURCE}" "$PLUGINSDIR\qx-node.exe"
    ${IfNot} ${Errors}
      ${StdUtils.HashFile} $R8 "SHA2-256" "$PLUGINSDIR\qx-node.exe"
      ${If} $R8 == "${QX_OLD_NODE_SHA}"
      ${OrIf} $R8 == "${QX_NEW_NODE_SHA}"
        StrCpy $qxNodeReady "1"
      ${EndIf}
    ${EndIf}
  ${EndIf}
!macroend

!macro qxPrepareBootstrapNode
  InitPluginsDir
  StrCpy $qxNodeReady "0"
  !insertmacro qxTryBootstrapNode "$INSTDIR\resources\workbench\runtime\node.exe"
  !insertmacro qxTryBootstrapNode "$INSTDIR\.qx-update-transaction\backup\resources\workbench\runtime\node.exe"
  !insertmacro qxTryBootstrapNode "$INSTDIR\.qx-update-transaction\work\resources\workbench\runtime\node.exe"
  !insertmacro qxTryBootstrapNode "$INSTDIR\.qx-update-transaction\patched\resources\workbench\runtime\node.exe"
  ${If} $qxNodeReady != "1"
    MessageBox MB_OK|MB_ICONEXCLAMATION "无法准备更新恢复程序。当前文件保持不变，请保留安装包并联系支持。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  File "/oname=$PLUGINSDIR\qx-incremental.cjs" "${QX_PATCH_RUNNER}"
!macroend

!macro qxRecoverInterruptedInstall
  !ifdef QX_PATCH_PLAN
    ${If} ${FileExists} "$INSTDIR\.qx-update-transaction\."
    ${OrIf} ${FileExists} "$INSTDIR\.qx-update.lock"
      !insertmacro qxPrepareBootstrapNode
      nsExec::ExecToStack '"$PLUGINSDIR\qx-node.exe" "$PLUGINSDIR\qx-incremental.cjs" recover "$INSTDIR"'
      Pop $0
      Pop $1
      ${If} $0 != 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "上次安装尚未完成恢复，请先关闭工作台及占用程序文件的窗口，再运行同一安装包重试。" /SD IDOK
        SetErrorLevel 1
        Quit
      ${EndIf}
    ${EndIf}
  !endif
!macroend
!endif
