import hou
import json
import os
import nodegraphutils


def current_parms_eval(kwargs):
    """
    Evaluate and store current node parameters for quick access.

    This method evaluates node parameters such as the Megascans asset, file format, geometry,
    and resolution, and stores them as attributes for easy retrieval later.
    """
    # Retrieve the user data containing Megascans information
    node = kwargs["node"]
    user_data = node.userDataDict().get("megascans_user_data")

    if user_data:
        # Dictionary mapping parameter names to their attribute names
        parms_to_eval = {
            "megascans_asset": "",
            "file_format": "",
            "render_geo": "",
            "proxy_geo": "",
            "resolution": "",
        }

        # Loop rough parameters and dynamically evaluate and assign them as class attributes
        for parm_name in parms_to_eval.keys():
            # Get parameter menu items
            menu_labels = node.parm(parm_name).menuItems()
            # Get current menu selection index
            menu_index = node.parm(parm_name).eval()
            # Set attribute to selected menu item
            parms_to_eval[parm_name] = menu_labels[
                menu_index
            ]  # Set attribute to selected menu item

        return parms_to_eval


def open_explorer(kwargs):
    """
    Open the file explorer to the current asset's directory if it exists.

    This function retrieves the asset path from the stored Megascans user data and opens the
    file explorer at the asset's directory. If the directory doesn't exist, an error message
    is displayed.
    """
    node = kwargs["node"]
    user_data = node.userDataDict().get("megascans_user_data")

    current_parms_dict = current_parms_eval(kwargs)
    current_asset = current_parms_dict["megascans_asset"]
    if node.parm("enable_batch_process").eval():
        current_asset = current_parms_dict["batch_asset"]

    if user_data:
        # Extract the asset path from the user data
        directory = json.loads(user_data)[current_asset]["path"]

        # Check if the directory exists and open it in the file explorer
        if os.path.isdir(directory):
            hou.ui.showInFileBrowser(directory)
        else:
            hou.ui.displayMessage(
                "Directory does not exist!"
            )  # Show error if directory is missing
    else:
        hou.ui.displayMessage(
            "User data not found!"
        )  # Show error if user data is missing


def find_id(kwargs):
    """
    Search for an asset by its ID and update the node parameter if found.

    This function searches the 'megascans_asset' parameter for an asset with a matching ID and
    updates the menu to select that asset if it is found. If the asset is not found, an error
    message is displayed.
    """
    node = kwargs["node"]
    # Get the search ID entered by the user
    search_parm = node.parm("batch_ids").eval()

    # Get the 'megascans_asset' parameter and its available options (menu labels)
    batch_menu = node.parm("batch_asset")
    assets_menu = node.parm("megascans_asset")
    batch_ids = node.parm("batch_ids")
    batch_assets = []

    if len(search_parm) > 0:
        # Search for an asset whose ID matches the entered search ID
        for asset_id in search_parm.split():
            menu_labels = assets_menu.menuLabels()
            matched_asset = [
                asset_id for item in menu_labels if asset_id == item.split("::")[-1]
            ]

            if matched_asset:
                # Set the parameter to the found asset's menu index
                batch_assets.append(matched_asset[0])
            else:
                # Display a message if no matching asset was found
                hou.ui.displayMessage(f"{asset_id} is not found in menu labels!")

        batch_ids.set(" ".join(batch_assets))
        batch_menu.pressButton()  # Press the button to refresh the node with the new asset
    # batch_menu.revertToDefaults()  # Revert to default value to avoid parameter lock
    node.cook(force=True)  # Recompute the node with new data


def get_asset_preview(kwargs):
    """Fetches the preview image path for the currently selected Megascans asset."""
    node = kwargs["node"]
    user_data = node.userDataDict().get("megascans_user_data")
    preview = None

    if user_data:

        current_parms_dict = current_parms_eval(kwargs)
        current_asset = current_parms_dict.get("megascans_asset")
        preview = json.loads(user_data).get(current_asset, {}).get("preview")

    asset_metadata = node.parm("asset_info").evalAsString()
    if not asset_metadata:
        return preview, None

    old_preview = json.loads(asset_metadata).get("preview")

    return preview, old_preview


def find_network_editors(kwargs):
    node = kwargs["node"]
    """Finds NetworkEditor panes displaying the node's parent."""
    return [
        pane
        for pane in hou.ui.paneTabs()
        if isinstance(pane, hou.NetworkEditor) and pane.pwd() == node.parent()
    ]


def add_background_image(kwargs, pane, preview):
    """Adds the preview image as a background in the given NetworkEditor pane."""
    node = kwargs["node"]
    bounds = hou.BoundingRect(-1, -1, 1, 1)
    bounds.translate(hou.Vector2(0.5, 1))  # Position adjustment

    image = hou.NetworkImage()
    image.setPath(preview)
    image.setRect(bounds)
    image.setRelativeToPath(node.path())

    pane.setBackgroundImages(list(pane.backgroundImages()) + [image])
    nodegraphutils.saveBackgroundImages(pane.pwd(), pane.backgroundImages())


def remove_background_image(pane, preview):
    """Removes the preview image from the given NetworkEditor pane."""
    images = [img for img in pane.backgroundImages() if img.path() != preview]
    if images:
        pane.setBackgroundImages(images)
        nodegraphutils.saveBackgroundImages(pane.pwd(), images)


def show_background_image(kwargs):
    """
    Adds or removes a background image in the NetworkEditor
    based on the 'show_background_image' parameter.
    """

    node = kwargs["node"]
    preview, old_preview = get_asset_preview(kwargs)
    panes = find_network_editors(kwargs)

    if node.parm("show_background_image").eval():
        for pane in panes:
            if old_preview:
                remove_background_image(pane, old_preview)
            if preview:
                add_background_image(kwargs, pane, preview)
    else:
        for pane in panes:
            remove_background_image(pane, preview)


def dump_info(kwargs, megascans_data):
    node = kwargs["node"]
    info_parm = node.parm("asset_info")
    info_parm.lock(False)
    info_parm.revertToDefaults()
    current_parms_dict = current_parms_eval(kwargs)
    if megascans_data:
        current_asset = current_parms_dict["megascans_asset"]
        asset_metadata = megascans_data[current_asset]
        node.parm("has_high").set(0)

        if "high" in [x.lower() for x in asset_metadata["lods"]]:
            node.parm("has_high").set(1)
        info_parm.set(json.dumps(asset_metadata, indent=4))
        info_parm.lock(True)
        return asset_metadata

    return None


def dirty_tx_pdg(node):
    node.parm("stringvalues").set(0)
    node.parm("dictattribs").set(0)
    topnet = hou.node(f"{node.path()}/topnet_convert_tx")
    topnet.dirtyAllWorkItems(remove_outputs=False)


def cook_tx_pdg(node):
    topnet = hou.node(f"{node.path()}/topnet_convert_tx")
    topnet.cookOutputWorkItems()


def switch_process_mode(kwargs):
    node = kwargs["node"]
    process_mode = kwargs["parm"].eval()
    assets_parm = node.parm("megascans_asset")
    pdg_index = node.parm("pdg_index")

    if process_mode == 1:
        assets_parm.set(pdg_index)
        assets_parm.lock(True)
        assets_parm.disable(True)
    else:
        assets_parm.disable(False)
        assets_parm.lock(False)
        assets_parm.deleteAllKeyframes()
    node.cook(force=True)
    assets_parm.pressButton()
