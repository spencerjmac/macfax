// Learn more: https://docs.expo.dev/guides/customizing-metro/
const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');
const path = require('path');

const projectRoot = __dirname;
// packages/core is a sibling source folder shared with web/. It is not an npm
// workspace, so Expo's automatic monorepo config does not pick it up.
const coreRoot = path.resolve(projectRoot, '../../packages/core');

const config = getDefaultConfig(projectRoot);

config.watchFolders = [coreRoot];
// Files under packages/core have no node_modules of their own: resolve any
// package they import from this app's node_modules.
config.resolver.nodeModulesPaths = [path.resolve(projectRoot, 'node_modules')];

module.exports = withNativeWind(config, { input: './global.css' });
