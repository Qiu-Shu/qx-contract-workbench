const fs=require('node:fs/promises');
const path=require('node:path');
function quoted(value){const text=path.resolve(value);if(/["$\r\n]/.test(text))throw Error('Unsupported NSIS build path');return '"'+text+'"';}
function replaceOnce(text,from,to){if(text.split(from).length!==2)throw Error('NSIS template changed; review the installer integration');return text.replace(from,to);}
async function customizeInstaller({output,templates,incremental,additionalIncrementals=[],sevenZip,sevenZipLicense,include=path.join(__dirname,'installer.nsh')}){
  await fs.mkdir(output,{recursive:true});
  // NSIS's built-in Include directory otherwise shadows electron-builder's
  // identically named multiUser.nsh after !cd. Keep its top-level includes together.
  for(const entry of await fs.readdir(templates))if(entry.endsWith('.nsh'))await fs.copyFile(path.join(templates,entry),path.join(output,entry));
  const assisted=await fs.readFile(path.join(templates,'assistedInstaller.nsh'),'utf8');
  const appendFolder='      ${StrContains} $0 "${APP_FILENAME}" $INSTDIR\n      ${If} $0 == ""\n        StrCpy $INSTDIR "$INSTDIR\\${APP_FILENAME}"\n      ${endIf}';
  // The directory page is the final choice, including existing custom locations.
  // Appending a product folder here would change the upgrade destination.
  const exactDirectory=replaceOnce(assisted,appendFolder,'      ; Keep the directory selected by the user.');
  await fs.writeFile(path.join(output,'assistedInstaller.nsh'),replaceOnce(exactDirectory,'    !include StrContains.nsh','    ; No automatic product subdirectory.'));
  let section=await fs.readFile(path.join(templates,'installSection.nsh'),'utf8');
  section=replaceOnce(section,'!include installer.nsh','!include installer.nsh\n!include '+quoted(path.join(__dirname,'installer-files.nsh')));
  const start=section.indexOf('!insertmacro uninstallOldVersion SHELL_CONTEXT');
  const end=section.indexOf('SetOutPath $INSTDIR',start);
  if(start<0||end<0)throw Error('NSIS uninstall section changed');
  section=section.slice(0,start)+'!insertmacro qxTryIncrementalInstall\n${If} $qxDeltaMode != "1"\n'+section.slice(start,end)+'${EndIf}\n\n'+section.slice(end);
  section=replaceOnce(section,'!insertmacro installApplicationFiles','${If} $qxDeltaMode == "1"\n  !insertmacro qxFinishIncrementalFiles\n${Else}\n  !insertmacro installApplicationFiles\n${EndIf}');
  section=replaceOnce(section,'!macro doStartApp','!insertmacro qxFinalizeIncrementalInstall\n\n!macro doStartApp');
  await fs.writeFile(path.join(output,'installSection.nsh'),section);
  const lines=[
    '; Keep the upstream installer/uninstaller generator; shadow only its install section.',
    '!addincludedir '+quoted(templates),
    '!cd '+quoted(output),
    '!include '+quoted(include),
    '!define QX_SEVEN_ZIP '+quoted(sevenZip),
    '!define QX_SEVEN_ZIP_LICENSE '+quoted(sevenZipLicense),
  ];
  if(incremental){
    const plan=JSON.parse(await fs.readFile(incremental.planFile,'utf8'));
    for(const v of [plan.fromVersion,plan.toVersion])if(!/^\d+\.\d+\.\d+$/.test(v))throw Error('Invalid incremental version');
    for(const v of [plan.bootstrapNode?.oldSha256,plan.bootstrapNode?.newSha256])if(!/^[a-f0-9]{64}$/.test(v))throw Error('Bootstrap Node digest missing');
    lines.push('!define QX_PATCH_FROM "'+plan.fromVersion+'"','!define QX_PATCH_TO "'+plan.toVersion+'"',
      '!define QX_OLD_NODE_SHA "'+plan.bootstrapNode.oldSha256+'"','!define QX_NEW_NODE_SHA "'+plan.bootstrapNode.newSha256+'"',
      '!define QX_PATCH_PLAN '+quoted(incremental.planFile),'!define QX_PATCH_FILE '+quoted(incremental.patchFile),
      '!define QX_PATCH_ENGINE '+quoted(incremental.hpatchz),'!define QX_PATCH_RUNNER '+quoted(path.join(__dirname,'incremental-install.cjs')));
    const versions=new Set();
    lines.push('!macro qxSelectPatch','  StrCpy $qxPatchFrom ""','  ${StdUtils.HashFile} $R8 "SHA2-256" "$INSTDIR\\resources\\app.asar"');
    for(const [index,item] of [incremental,...additionalIncrementals].entries()){
      const other=JSON.parse(await fs.readFile(item.planFile,'utf8'));
      if(!/^\d+\.\d+\.\d+$/.test(other.fromVersion)||versions.has(other.fromVersion)||other.toVersion!==plan.toVersion||other.targetMarker.sha256!==plan.targetMarker.sha256||other.bootstrapNode.oldSha256!==plan.bootstrapNode.oldSha256)throw Error('Incompatible upgrade baseline');
      versions.add(other.fromVersion);
      if(!/^[a-f0-9]{64}$/.test(other.baseMarker.sha256))throw Error('Invalid baseline marker');
      // Recovery can roll files back before NSIS repairs DisplayVersion; select by bytes.
      lines.push('  ${If} $R8 == "'+other.baseMarker.sha256+'"');
      if(index===0)lines.push('  ${OrIf} $R8 == "'+plan.targetMarker.sha256+'"');
      lines.push('    StrCpy $qxPatchFrom "'+other.fromVersion+'"',
        '    ${If} $R8 == "'+plan.targetMarker.sha256+'"',
        '      StrCpy $qxPatchFrom "'+plan.toVersion+'"',
        '    ${EndIf}',
        '    File "/oname=$PLUGINSDIR\\qx-plan.json" '+quoted(item.planFile),
        '    File "/oname=$PLUGINSDIR\\qx-changes.hdiff" '+quoted(item.patchFile),
        '  ${EndIf}');
    }
    lines.push('!macroend');
  }
  lines.push('!include '+quoted(path.join(__dirname,'installer-bootstrap.nsh')));
  const result=path.join(output,'qx-installer-include.nsh');await fs.writeFile(result,lines.join('\n')+'\n');return result;
}
module.exports={customizeInstaller};
