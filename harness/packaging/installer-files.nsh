; This include runs after electron-builder has declared installApplicationFiles.
Var /GLOBAL qxDeltaMode

; Unpack once into the final application directory. The old program is only
; uninstalled on the full-install route; the delta route never calls this macro.
!macroundef extractUsing7za
!macro extractUsing7za FILE
  InitPluginsDir
  File "/oname=$PLUGINSDIR\qx-7za.exe" "${QX_SEVEN_ZIP}"
  DetailPrint "正在展开程序文件…"
  nsExec::ExecToLog '"$PLUGINSDIR\qx-7za.exe" x "${FILE}" "-o$INSTDIR" -y -bso0 -bsp0'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "程序文件未能完整展开，请检查可用空间后重新安装。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  SetOutPath "$INSTDIR\resources"
  File "/oname=7zip-LICENSE.txt" "${QX_SEVEN_ZIP_LICENSE}"
  SetOutPath "$INSTDIR"
!macroend

!macro qxRollbackIncrementalInstall
  nsExec::ExecToStack '"$PLUGINSDIR\qx-node.exe" "$PLUGINSDIR\qx-incremental.cjs" rollback "$INSTDIR"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion "${QX_PATCH_FROM}"
    MessageBox MB_OK|MB_ICONEXCLAMATION "更新未完成，已恢复原程序。请关闭占用程序文件的窗口后重试。" /SD IDOK
  ${ElseIf} $0 == 10
    MessageBox MB_OK|MB_ICONEXCLAMATION "程序文件已更新，安装信息尚待完成，请重新运行同一安装包完成更新。" /SD IDOK
  ${Else}
    MessageBox MB_OK|MB_ICONEXCLAMATION "更新尚未完成恢复，请关闭占用程序文件的窗口，再运行同一安装包继续恢复。" /SD IDOK
  ${EndIf}
  SetErrorLevel 1
  Quit
!macroend

!macro qxTryIncrementalInstall
  StrCpy $qxDeltaMode "0"
  ${If} $installMode != "CurrentUser"
    MessageBox MB_OK|MB_ICONEXCLAMATION "此安装包仅支持当前 Windows 用户安装，原程序保持不变。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ${If} $perUserInstallationFolder != ""
  ${AndIf} $INSTDIR != $perUserInstallationFolder
    MessageBox MB_OK|MB_ICONEXCLAMATION "已有安装需要沿用原目录升级，请返回选择原安装目录。首次安装可以自由选择位置。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  !ifdef QX_PATCH_PLAN
    ReadRegStr $0 SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion
    ${If} ${FileExists} "$INSTDIR\resources\app.asar"
    ${AndIf} ${FileExists} "$INSTDIR\resources\workbench\runtime\node.exe"
      ${If} $0 == "${QX_PATCH_FROM}"
      ${OrIf} $0 == "${QX_PATCH_TO}"
        !insertmacro qxPrepareBootstrapNode
        File "/oname=$PLUGINSDIR\qx-plan.json" "${QX_PATCH_PLAN}"
        File "/oname=$PLUGINSDIR\qx-changes.hdiff" "${QX_PATCH_FILE}"
        File "/oname=$PLUGINSDIR\qx-hpatchz.exe" "${QX_PATCH_ENGINE}"
        DetailPrint "正在更新变化的程序文件，未变化文件保持原位…"
        nsExec::ExecToStack '"$PLUGINSDIR\qx-node.exe" "$PLUGINSDIR\qx-incremental.cjs" apply "$INSTDIR" "$PLUGINSDIR\qx-plan.json" "$PLUGINSDIR\qx-changes.hdiff" "$PLUGINSDIR\qx-hpatchz.exe"'
        Pop $0
        Pop $1
        ${If} $0 != 0
          MessageBox MB_OK|MB_ICONEXCLAMATION "未能完成增量更新。原程序已保留或进入恢复流程；请关闭占用程序文件的窗口，再运行同一安装包重试。" /SD IDOK
          SetErrorLevel 1
          Quit
        ${EndIf}
        StrCpy $qxDeltaMode "1"
      ${EndIf}
    ${EndIf}
  !endif
  ${If} $qxDeltaMode != "1"
  ${AndIf} $perUserInstallationFolder != ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "当前已安装版本不适用这个增量包，原程序和自加文件保持不变。请使用对应版本的更新包。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ${If} $qxDeltaMode != "1"
  ${AndIf} ${isUpdated}
    MessageBox MB_OK|MB_ICONEXCLAMATION "此版本无法使用当前增量安装包，现有程序保持不变。请从发布页面手动下载安装包。" /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  ; A full first installation must not mix application files into an unrelated
  ; folder. Existing registered installations only use the verified delta above.
  ${If} $qxDeltaMode != "1"
    FindFirst $R0 $R1 "$INSTDIR\*.*"
    qx_check_empty:
      ${If} $R1 == ""
        Goto qx_empty_done
      ${EndIf}
      ${If} $R1 != "."
      ${AndIf} $R1 != ".."
        FindClose $R0
        MessageBox MB_OK|MB_ICONEXCLAMATION "首次安装请选择一个空文件夹，现有文件保持不变。" /SD IDOK
        SetErrorLevel 1
        Quit
      ${EndIf}
      FindNext $R0 $R1
      Goto qx_check_empty
    qx_empty_done:
    FindClose $R0
  ${EndIf}
!macroend

!macro qxFinishIncrementalFiles
  !ifdef QX_PATCH_PLAN
    SetOutPath "$INSTDIR"
    ClearErrors
    File "/oname=${UNINSTALL_FILENAME}" "${UNINSTALLER_OUT_FILE}"
    ${If} ${Errors}
      !insertmacro qxRollbackIncrementalInstall
    ${EndIf}
    ; Keep the standard cache identity so the next blockmap download uses this EXE.
    !insertmacro copyFile "$EXEPATH" "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
    ${If} ${Errors}
      !insertmacro qxRollbackIncrementalInstall
    ${EndIf}
  !endif
!macroend

!macro qxFinalizeIncrementalInstall
  !ifdef QX_PATCH_PLAN
    ${If} $qxDeltaMode == "1"
      ReadRegStr $0 SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" DisplayVersion
      ${If} $0 != "${QX_PATCH_TO}"
        !insertmacro qxRollbackIncrementalInstall
      ${EndIf}
      nsExec::ExecToStack '"$PLUGINSDIR\qx-node.exe" "$PLUGINSDIR\qx-incremental.cjs" finalize "$INSTDIR"'
      Pop $0
      Pop $1
      ${If} $0 != 0
        !insertmacro qxRollbackIncrementalInstall
      ${EndIf}
      DetailPrint "增量安装已完成。"
    ${EndIf}
  !endif
!macroend
