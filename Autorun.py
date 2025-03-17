import hou
from importlib import reload
import MegascansData
import Build

reload(MegascansData)
reload(Build)

# Get the current Houdini node
node = hou.pwd()

# Evaluate the parameter 'library_path'
library_path = node.parm("library_path").evalAsString()

# Initialize the MegascansData
MegascansData.set_megascans_data(node, library_path)
# Build.load_asset(node)
# Build.build_materials(node)

# topnet = hou.node("./topnet")
# topnet.dirtyAllWorkItems(remove_outputs=False)
# topnet.generateStaticWorkItems()
