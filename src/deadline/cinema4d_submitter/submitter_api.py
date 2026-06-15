# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from deadline.client.submitter_api import SubmitterAPI, SubmitterSettings


@dataclass
class Cinema4DSubmitterSettings(SubmitterSettings):
    """Cinema 4D-specific submission settings."""

    renderer: str = ""
    take_name: str = ""
    image_width: int = 1920
    image_height: int = 1080
    description: str = ""


class Cinema4DSubmitterAPI(SubmitterAPI):
    """SubmitterAPI implementation for Cinema 4D submissions."""

    def get_settings(self) -> Cinema4DSubmitterSettings:
        import c4d  # type: ignore[import]

        settings = Cinema4DSubmitterSettings()
        doc = c4d.documents.GetActiveDocument()

        settings.name = doc.GetDocumentName() or "Untitled"
        settings.project_path = doc.GetDocumentPath() or ""

        scene_file = (
            os.path.join(settings.project_path, settings.name) if settings.project_path else ""
        )
        settings.input_filenames = [scene_file] if scene_file else []

        rd = doc.GetActiveRenderData()
        if rd:
            fps = doc.GetFps()
            start_frame = rd[c4d.RDATA_FRAMEFROM].GetFrame(fps)
            end_frame = rd[c4d.RDATA_FRAMETO].GetFrame(fps)
            settings.frame_list = f"{start_frame}-{end_frame}"

            settings.image_width = int(rd[c4d.RDATA_XRES])
            settings.image_height = int(rd[c4d.RDATA_YRES])

            output_path = rd[c4d.RDATA_PATH]
            if output_path:
                settings.output_path = os.path.dirname(output_path)
                settings.output_directories = [settings.output_path]

            renderer_id = rd[c4d.RDATA_RENDERENGINE]
            settings.renderer = str(renderer_id)

        take_data = doc.GetTakeData()
        if take_data:
            current_take = take_data.GetCurrentTake()
            if current_take:
                settings.take_name = current_take.GetName()

        return settings

    def get_job_template(
        self,
        settings: SubmitterSettings,
        host_requirements: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        import yaml
        from pathlib import Path

        with open(Path(__file__).parent / "default_cinema4d_job_template.yaml") as fh:
            job_template = yaml.safe_load(fh)

        job_template["name"] = settings.name

        if isinstance(settings, Cinema4DSubmitterSettings) and settings.description:
            job_template["description"] = settings.description

        if host_requirements:
            for step in job_template.get("steps", []):
                step["hostRequirements"] = host_requirements

        return job_template

    def get_parameter_values(
        self,
        settings: SubmitterSettings,
        queue_parameters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        import c4d  # type: ignore[import]

        doc = c4d.documents.GetActiveDocument()
        scene_file = os.path.join(doc.GetDocumentPath() or "", doc.GetDocumentName() or "")

        parameter_values: list[dict[str, Any]] = [
            {"name": "Cinema4DFile", "value": scene_file},
            {"name": "Frames", "value": settings.frame_list},
            {"name": "deadline:priority", "value": settings.priority},
            {"name": "deadline:targetTaskRunStatus", "value": settings.initial_status},
            {"name": "deadline:maxFailedTasksCount", "value": settings.max_failed_tasks_count},
            {"name": "deadline:maxRetriesPerTask", "value": settings.max_retries_per_task},
        ]

        if isinstance(settings, Cinema4DSubmitterSettings) and settings.take_name:
            parameter_values.append({"name": "Take", "value": settings.take_name})

        parameter_values.extend(
            {"name": param["name"], "value": param["value"]} for param in queue_parameters
        )

        return parameter_values

    def get_asset_references(self, settings: SubmitterSettings) -> dict[str, Any]:
        from .assets import AssetIntrospector
        from deadline.client.job_bundle.submission import AssetReferences

        introspector = AssetIntrospector()
        assets = introspector.collect_assets()

        input_filenames = set()
        for asset in assets:
            path = str(asset)
            if os.path.isfile(path):
                input_filenames.add(path)

        if settings.input_filenames:
            input_filenames.update(settings.input_filenames)

        asset_refs = AssetReferences(
            input_filenames=input_filenames,
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )
        return asset_refs.to_dict()
