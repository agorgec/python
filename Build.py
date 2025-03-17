import hou
from importlib import reload
import json
import os
import Utilities
import voptoolutils

reload(Utilities)


def build_asset(kwargs):
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

    node = kwargs["node"]
    if not node.userDataDict().get("megascans_user_data"):
        return

    megascans_user_data = json.loads(node.userDataDict().get("megascans_user_data"))
    Utilities.dump_info(node, megascans_user_data)

    render_geo_loader = hou.node("./sopnet/asset_loader_render")
    render_format_switch = hou.node("./sopnet/render_format_switch")
    proxy_geo_loader = hou.node("./sopnet/asset_loader_proxy")
    get_var = hou.node("./sopnet/get_var")

    current_parms = Utilities.current_parms_eval(node)
    asset_info = json.loads(node.parm("asset_info").evalAsString())
    file_format = current_parms["file_format"]

    get_asset_size(node)

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
    current_asset = current_parms["megascans_asset"]
    print(node.parm("enable_batch_process").eval())
    if node.parm("enable_batch_process").eval():
        current_asset = current_parms["batch_asset"]
    node.parm("asset_name").set("_".join(current_asset.split("::")[1:]))
    node.parm("has_var").set(get_var.geometry().attribValue("has_var"))

    var_num = get_var.geometry().attribValue("var_num") + 1
    node.parm("var_num_message").set(f" Number of Variants: {var_num}")
    node.parm("var_num").set(var_num)


def build_materials(kwargs):
    """
    Build materials based on the asset's material data.

    Args:
        node (hou.Node): Houdini node containing Megascans asset data.
    """
    node = kwargs["node"]
    clean_material_library(node)
    create_matlib_content(node)
    textures = get_textures(node)
    missing_tx(node, textures)


def get_matlib(node):
    """
    Get the path to the material library.
    """
    return hou.node(node.path() + "/material_library")


def clean_material_library(node):
    """
    Remove all materials from the material library.
    """
    matlib = get_matlib(node)
    matlib.deleteItems(matlib.children())


def create_matlib_content(node):
    matlib = get_matlib(node)
    kma_shader = voptoolutils._setupMtlXBuilderSubnet(
        destination_node=matlib,
        name="kma_shader",
        mask=voptoolutils.KARMAMTLX_TAB_MASK,
        folder_label="Karma Material Builder",
        render_context="kma",
    )
    preview_shader = voptoolutils._setupUsdPreviewBuilderSubnet(
        destination_node=matlib,
    )

    kma_shader.setGenericFlag(hou.nodeFlag.Material, False)
    collect = matlib.createNode("collect", "OUT_material")

    collect.setInput(0, kma_shader, 0)
    collect.setInput(1, kma_shader, 1)
    collect.setInput(2, kma_shader, 2)

    matlib.layoutChildren(horizontal_spacing=2)
    create_image_files(node, kma_shader)


def get_asset_size(node):
    batch_process = node.parm("enable_batch_process").eval()
    if batch_process:
        batch_ids = node.parm("batch_ids").evalAsString().split()
        node.parm("stringvalues").set(len(batch_ids))
        for index, batch_id in enumerate(batch_ids):
            node.parm(f"stringvalue{index + 1}").set(batch_id)
    else:
        current_parms = Utilities.current_parms_eval(node)
        current_asset = current_parms["megascans_asset"]
        asset_id = current_asset.split("::")[-1]
        node.parm("stringvalues").set(1)
        node.parm("stringvalue1").set(asset_id)


def missing_tx(node, textures=[]):
    if not textures:
        textures = get_textures(node)
    to_generate = {}
    for tx in textures:
        rat_file = os.path.splitext(tx[1])[0] + ".rat"
        if not os.path.exists(rat_file):
            to_generate[tx[0]] = tx[1]

    node.parm("dictattribs").set(0)
    if to_generate:
        node.parm("dictattribs").set(1)
        node.parm("dictname1").set("textures")
        node.parm("dictvalue1").set(json.dumps(to_generate))

        node.parm("_cook_controls_cookoutputnode").pressButton()


def get_textures(node):
    """
    Set the current textures for the asset based on resolution and LOD.

    Args:
        megascans_data (dict): Data containing textures for the current asset.

    Returns:
        list: A list of tuples containing texture type, file path, and colorspace.
    """
    textures_dict = json.loads(node.parm("asset_info").evalAsString())["textures"]
    # auto_tx = self.utilities.node.parm("auto_tx").eval()
    render_geo_lod = Utilities.current_parms_eval(node)["render_geo"]
    current_res = Utilities.current_parms_eval(node)["resolution"]
    current_textures = []

    # Loop through each texture type and select the appropriate resolution
    for tx_type, tx_type_values in textures_dict.items():
        textures = tx_type_values["resolution"][current_res]
        # Select texture matching the LOD, fallback to the first if no match found
        found_tx = next(
            (texture for texture in textures if render_geo_lod in texture),
            textures[0],
        )
        exr_file = os.path.splitext(found_tx)[0] + ".exr"
        if os.path.exists(exr_file):
            found_tx = exr_file
        #     # Automatically convert textures if auto_tx is enabled
        #     if auto_tx:
        #         self.convert_textures(found_tx)

        current_textures.append((tx_type, found_tx, tx_type_values["colorSpace"]))

    return current_textures


def create_image_files(node, shader):
    textures = get_textures(node)
    surface = hou.node(shader.path() + "/mtlxstandard_surface")
    displacement = hou.node(shader.path() + "/mtlxdisplacement")
    not_used_textures = []

    for texture in textures:
        tx_type, tx_path, tx_colorspace = texture
        tx_image = shader.createNode("mtlximage", tx_type.upper())
        tx_image.parm("file").set(tx_path)
        tx_image.setColor(hou.Color((0.71, 0.518, 0.004)))
        if tx_type.lower() == "albedo":
            surface.setNamedInput("base_color", tx_image, "out")
        elif tx_type.lower() == "roughness":
            surface.setNamedInput("specular_roughness", tx_image, "out")
        elif tx_type.lower() == "normal":
            normal_map = shader.createNode("mtlxnormalmap")
            normal_map.parm("scale").set(0.01)
            normal_map.setInput(0, tx_image)
            surface.setNamedInput("normal", normal_map, "out")
        elif tx_type.lower() == "displacement":
            tx_image.parm("signature").set("float")
            displacement.parm("scale").set(0.01)
            remap = shader.createNode("mtlxremap")
            remap.parm("outlow").set(-0.5)
            remap.parm("outhigh").set(0.5)
            remap.setInput(0, tx_image)
            displacement.setNamedInput("displacement", remap, "out")
        elif tx_type.lower() in surface.inputNames():
            surface.setNamedInput(tx_type.lower(), tx_image, "out")
        else:
            not_used_textures.append(tx_image)

    clean_matnet(shader, not_used_textures)


def clean_matnet(shader, not_used_textures):
    """
    Clean up the shader network by removing unused texture nodes and organizing the layout.

    Args:
        shader (hou.Node): Shader node containing texture nodes to clean up.
        not_used_textures (list): List of unused texture image nodes.
    """
    shader.layoutChildren(horizontal_spacing=2)

    # Create a network box for unused textures and arrange their layout
    networkbox = shader.createNetworkBox()
    for image in not_used_textures:
        networkbox.addItem(image)
    networkbox.fitAroundContents()
    networkbox.setMinimized(True)
    # networkbox.setPosition((min_pos[0], min_pos[1] - 3))
    networkbox.setComment("Textures Not Used")
