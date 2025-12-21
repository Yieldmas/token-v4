// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {LibFacetVersionStorage, VersionTypes} from "src/abstract-diamond/storage/LibFacetVersionStorage.sol";

contract VersioningFacet {
    /// @notice Get the version metadata for a given facet address
    /// @param facetName The facet address
    /// @return metadata The version metadata
    function getFacetMetadata(
        string memory facetName
    ) external view returns (VersionTypes.Metadata memory metadata) {
        metadata = LibFacetVersionStorage.getFacetMetadata(facetName);
    }
}
