function navigationAllowed(url, origin, setup) {
  if (url === setup) return true;
  try {
    const parsed = new URL(url);
    return Boolean(origin && parsed.protocol === 'http:' && parsed.origin === origin && !parsed.username && !parsed.password);
  } catch { return false; }
}
function setupSenderAllowed(url, setup, isMainFrame) {
  return isMainFrame && url === setup;
}
function validLibraryRoot(root) {
  const fs = require('node:fs'), path = require('node:path');
  try {
    return path.isAbsolute(root) && ['catalog.sqlite','current.json'].every(name => {
      const file = fs.lstatSync(path.join(root,name));
      return file.isFile() && !file.isSymbolicLink() && file.nlink === 1;
    });
  } catch { return false; }
}
module.exports = { navigationAllowed, setupSenderAllowed, validLibraryRoot };
