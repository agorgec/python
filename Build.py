import hou
from importlib import reload
import json
import Utilities

reload(Utilities)


def load_asset(node):
    """
    Load the asset's geometry files based on LOD settings and set asset-specific parameters.

    Args:
        node (hou.Node): Houdini node containing Megascans asset data.
    """

    def get_filtered_files(lod_list, file_format):
        return [file for file in lod_list if file.endswith(f".{file_format}")]

    def set_geo_loader_params(loader, files):
        loader.parm("files").set(len(files))
        for index, file in enumerate(files):
            file_parm = loader.parm(f"filelist{index + 1}")
            if file_parm.evalAsString() != file:
                file_parm.set(file)

    if not node.userDataDict().get("megascans_user_data"):
        return

    render_geo_loader = hou.node("./sopnet/asset_loader_render")
    render_format_switch = hou.node("./sopnet/render_format_switch")
    proxy_geo_loader = hou.node("./sopnet/asset_loader_proxy")
    get_var = hou.node("./sopnet/get_var")

    current_parms = Utilities.current_parms_eval(node)
    asset_info = json.loads(node.parm("asset_info").evalAsString())
    file_format = current_parms["file_format"]

    # Load Render Geometry
    render_lod = (
        "HIGH"
        if node.parm("load_original").eval() == 1
        and not node.parm("load_original").isDisabled()
        else current_parms["render_geo"]
    )
    render_geo_files = get_filtered_files(asset_info["lods"][render_lod], file_format)
    set_geo_loader_params(render_geo_loader, render_geo_files)

    # Set render format switch
    render_format_switch.parm("input").set(0 if file_format == "abc" else 1)

    # Load Proxy Geometry
    proxy_geo_files = get_filtered_files(
        asset_info["lods"][current_parms["proxy_geo"]], file_format
    )
    set_geo_loader_params(proxy_geo_loader, proxy_geo_files)

    # Set asset parameters
    node.parm("asset_name").set(
        "_".join(current_parms["megascans_asset"].split("::")[1:])
    )
    node.parm("has_var").set(get_var.geometry().attribValue("has_var"))

    var_num = get_var.geometry().attribValue("var_num") + 1
    node.parm("var_num_message").set(f" Number of Variants: {var_num}")
    node.parm("var_num").set(var_num)
