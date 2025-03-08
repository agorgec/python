import os
import re
from pathlib import Path
from importlib import reload
import json
import Utilities

reload(Utilities)


def set_megascans_data(node, library_path):
    """
    Loads asset data from a Megascans asset library, processes it, and sets user data on the node.

    Args:
        node: Houdini node where processed asset data will be stored.
        library_path (str or Path): Path to the Megascans asset library.
    """
    assets_data_path = Path(library_path) / "Downloaded" / "assetsData.json"
    megascans_data = {}

    # Check if the asset data JSON file exists
    if os.path.isfile(assets_data_path):
        with open(assets_data_path, "r", encoding="utf-8") as file:
            assets_data = json.load(file)

        for data in assets_data:
            asset_name = "_".join(data["name"].split())  # Normalize asset name
            asset_type = data["type"]
            asset_id = data["id"]

            # Construct the asset path using provided library structure
            asset_path = Path(library_path) / "Downloaded" / "/".join(data["path"])

            # Resolve asset textures, LODs, and formats
            asset_textures, asset_lods, asset_formats = resolve_assets(
                asset_type, asset_id, asset_path
            )

            # Create metadata dictionary for the asset
            metadata = {
                "name": asset_name,
                "id": asset_id,
                "path": asset_path.as_posix(),
                "type": asset_type,
                "formats": asset_formats,
                "lods": asset_lods,
                "textures": asset_textures,
                "tags": data["tags"],
            }

            # Store metadata in a dictionary with a unique key
            megascans_data[f"{asset_type}::{asset_name}::{asset_id}"] = metadata

    # Store asset data as user data on the node and update parameters
    set_user_data(node, megascans_data)
    dump_info(node, megascans_data)
    node.cook(force=True)  # Recompute the node with new data


def resolve_assets(asset_type, asset_id, asset_path):
    """
    Resolves asset textures, LODs, and formats based on asset type.

    Args:
        asset_type (str): Type of the asset (e.g., "3d" or "3dplant").
        asset_id (str): Unique identifier of the asset.
        asset_path (str or Path): Path to the asset's directory.

    Returns:
        tuple: (textures_dict, lods_dict, formats_list) containing:
            - textures_dict (dict): Texture paths and metadata.
            - lods_dict (dict): Level of Detail (LOD) file paths.
            - formats_list (list): List of file formats present.
    """
    if asset_type in ("3d", "3dplant"):
        # Load asset metadata from JSON file
        with open(f"{asset_path}/{asset_id}.json", "r", encoding="utf-8") as file:
            asset_data = json.load(file)

        if asset_type == "3d":
            # Resolve 3D asset textures and LODs
            asset_textures = resolve_3d_tx(asset_path, asset_data)
            asset_lods, asset_formats = resolve_3d(asset_path, asset_data)
        else:
            # Resolve 3D plant asset textures and LODs
            asset_textures = resolve_3dplant_tx(asset_path, asset_data)
            asset_lods, asset_formats = resolve_3dplant(asset_path, asset_data)

        return asset_textures, asset_lods, asset_formats


def resolve_3d_tx(asset_path, asset_data):
    """
    Resolves texture file paths for 3D assets by checking both maps and components.

    Args:
        asset_path (str or Path): Path to the asset's directory.
        asset_data (dict): Dictionary containing asset metadata.

    Returns:
        dict: A dictionary mapping texture names to their types, color spaces,
              and resolution-specific file paths.
    """
    asset_path_obj = Path(asset_path)

    # Try resolving from maps first
    tx_dict = resolve_3d_tx_maps(asset_path_obj, asset_data.get("maps", []))
    if tx_dict:  # If texture maps exist, return early
        return tx_dict

    # If no maps were found, try resolving from components
    return resolve_3d_tx_components(asset_path_obj, asset_data.get("components", []))


def resolve_3d_tx_maps(asset_path_obj, maps):
    """
    Resolves texture maps for 3D assets.

    Args:
        asset_path_obj (Path): Path object pointing to the asset directory.
        maps (list): List of texture map metadata.

    Returns:
        dict: A dictionary mapping texture names to their paths, if found.
    """
    tx_dict = {}

    for tx_map in maps:
        file_path = asset_path_obj / tx_map["uri"]
        if not file_path.exists():  # Skip missing files
            continue

        name = tx_map["name"]
        resolution = tx_map["resolution"]

        # Initialize dictionary structure if the texture name is new
        tx_dict.setdefault(
            name,
            {
                "type": tx_map["type"],
                "colorSpace": tx_map["colorSpace"],
                "resolution": {},
            },
        )

        # Append the file path under the corresponding resolution
        tx_dict[name]["resolution"].setdefault(resolution, []).append(
            file_path.as_posix()
        )

    return tx_dict  # Return dictionary containing resolved maps


def resolve_3d_tx_components(asset_path_obj, components):
    """
    Resolves texture components for 3D assets.

    Args:
        asset_path_obj (Path): Path object pointing to the asset directory.
        components (list): List of texture component metadata.

    Returns:
        dict: A dictionary mapping component names to their texture paths.
    """
    tx_dict = {}

    for component in components:
        texture_paths = {}

        for uri in component.get("uris", []):
            for resolution_data in uri.get("resolutions", []):
                # Collect valid texture file paths
                textures = [
                    (asset_path_obj / tx_format["uri"]).as_posix()
                    for tx_format in resolution_data.get("formats", [])
                    if (asset_path_obj / tx_format["uri"]).exists()
                ]
                if textures:  # Only store resolutions with valid textures
                    texture_paths[resolution_data["resolution"]] = textures

        if texture_paths:  # Store component only if it contains valid textures
            tx_dict[component["name"]] = {
                "type": component["type"],
                "colorSpace": component["colorSpace"],
                "resolution": texture_paths,
            }

    return tx_dict  # Return dictionary containing resolved components


def resolve_3d(asset_path, asset_data):
    mesh_dict = {}
    formats = set()

    # Choose the key to process: "meshes" or "models"
    key = "meshes" if asset_data.get("meshes") else "models"
    if key not in asset_data:
        return mesh_dict, list(formats)

    for mesh in asset_data[key]:
        # Handle both "uris" (list) and "uri" (single) structures
        uris = mesh.get("uris") or [mesh]
        for uri_data in uris:
            uri = uri_data["uri"]
            file_path = Path(asset_path) / uri

            if file_path.exists():
                lod_match = re.findall(r"(high|lod\d)", uri.lower())
                if lod_match:
                    lod = lod_match[0].upper()
                    formats.add(file_path.suffix.lstrip("."))
                    mesh_dict.setdefault(lod, []).append(file_path.as_posix())

    return mesh_dict, list(formats)


def resolve_3dplant_tx(asset_path, asset_data):
    tx_dict = {}

    for tx_map in asset_data["maps"]:
        texture_paths = {}
        textures = []
        file_path = Path(asset_path) / tx_map["uri"]

        if file_path.exists():
            textures.append(file_path.as_posix())
            texture_paths.update({tx_map["resolution"]: textures})
            tx_dict.update(
                {
                    tx_map["name"]: {
                        "type": tx_map["type"],
                        "colorSpace": tx_map["colorSpace"],
                        "resolution": texture_paths,
                    }
                }
            )

    return tx_dict


def resolve_3dplant(asset_path, asset_data):
    mesh_dict = {}
    formats = set()

    for model in asset_data["models"]:
        file_path = Path(asset_path) / model["uri"]

        if file_path.exists():
            geo = model["uri"]
            lod = geo.rsplit("_", maxsplit=1)[1].split(".")[0].upper()
            formats.add(file_path.suffix.lstrip("."))

            if lod in model["uri"].upper():
                if mesh_dict.get(lod) is None:
                    mesh_dict[lod] = []

                mesh_dict[lod].extend([file_path.as_posix()])

    return mesh_dict, list(formats)


def set_user_data(node, megascans_data):
    node.destroyUserData("megascans_user_data", must_exist=False)
    if megascans_data:
        user_data = json.dumps(megascans_data, indent=4)
        node.setUserData("megascans_user_data", user_data)


def dump_info(node, megascans_data):
    info_parm = node.parm("asset_info")
    info_parm.lock(False)
    current_parms_dict = Utilities.current_parms_eval(node)

    if megascans_data:
        current_asset = current_parms_dict["megascans_asset"]
        asset_metadata = megascans_data[current_asset]
        node.parm("has_high").set(0)

        if "high" in [x.lower() for x in asset_metadata["lods"]]:
            node.parm("has_high").set(1)
        info_parm.set(json.dumps(asset_metadata, indent=4))
        info_parm.lock(True)

    else:
        info_parm.set("")
