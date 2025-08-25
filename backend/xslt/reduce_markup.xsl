<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet 
  version="3.0"
  xpath-default-namespace="http://www.tei-c.org/ns/1.0" 
  xmlns:hei="https://digi.ub.uni-heidelberg.de/schema/tei/heiEDITIONS"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  >

<!-- 
    
-->  
     
  <xsl:output method="xml"/>

  <!-- Identity template -->
  <xsl:mode on-no-match="shallow-copy" />

  <xsl:param name="editorial" as="xs:boolean" select="false()"/>
  
    <xsl:template match="w | c | choice | pc | g">
        <xsl:apply-templates select="node()"/>
    </xsl:template>

    <xsl:template match="orig | sic | abbr">
        <xsl:choose>
            <xsl:when test="$editorial">
            </xsl:when>
            <xsl:otherwise>
                <xsl:apply-templates select="@*|node()"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="reg | corr | expan">
        <xsl:if test="$editorial">
            <xsl:apply-templates select="@*|node()"/>
        </xsl:if>
    </xsl:template>
  
  
  
</xsl:stylesheet>
